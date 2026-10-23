"""NiSH Player: a small multitrack player with speed, pitch, Auto 440 and export."""
import gc
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

import engine  # noqa: E402  (sets up PATH for the bundled ffmpeg)
from engine import APP_NAME  # noqa: E402

LOG_FILE = engine.DATA_DIR / "log.txt"
# A windowed .exe has no console; send stray prints to a log file instead of crashing.
if sys.stdout is None or sys.stderr is None:
    _log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

import tkinter as tk  # noqa: E402
from tkinter import messagebox  # noqa: E402

import customtkinter as ctk  # noqa: E402

TkinterDnD = DND_FILES = None
if not os.environ.get("NISH_NO_DND"):
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES  # noqa: F811
    except Exception:
        TkinterDnD = None

from theme import *  # noqa: E402,F401,F403
import settings  # noqa: E402
import theme  # noqa: E402
import updater  # noqa: E402
from export_dialog import ExportDialog  # noqa: E402
from lane import Lane  # noqa: E402
from layout import LayoutMixin  # noqa: E402
from project_ui import ProjectMixin  # noqa: E402
from speed_pitch import SpeedPitchMixin  # noqa: E402
from tracks import TracksMixin  # noqa: E402


def splitter_is_url(src):
    import splitter
    return splitter.is_url(str(src or ""))



# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class App(LayoutMixin, TracksMixin, SpeedPitchMixin, ProjectMixin):
    """The main window. Its parts live in layout.py, tracks.py, speed_pitch.py and project_ui.py."""

    def __init__(self, root):
        self.root = root
        self.player = engine.Player()
        self.events = queue.Queue()
        self.player.on_render_done = lambda: self.events.put(("render",))
        self.lanes = []
        self.loading = 0
        self.speed, self.semis, self.manual_cents = 1.0, 0, 0.0
        self.auto = False
        self.auto_result = None      # (correction_cents, A_hz, confidence)
        self.alert_win = None
        self.analysing = False
        self._analysis_gen = 0
        self._stretch_job = None
        self.export_dialog = None
        self.split_job = None
        self.split_pop = None
        self.selected = None
        self._drag = None
        self._split_status = None
        self.last_dir = settings.desktop()    # Open… starts on the Desktop
        self.project_path = None     # the open project (.nish), if any
        self._saved_sig = None       # project state when last saved/opened
        self._restore = None         # settings waiting for tracks that are still loading
        self.recent_pop = None
        self.vol_pop = None          # compact lanes: the V volume popover
        self.auto_tip = None         # value tip over an automation point
        self._resize = None          # (start y, start height) while dragging a lane edge
        self._resize_hint = None
        try:
            h = int(settings.get("track_height", Lane.H_DEF))
        except (TypeError, ValueError):
            h = Lane.H_DEF
        self.track_h = max(Lane.H_MIN, min(Lane.H_MAX, h))      # one height for every lane (remembered)
        self.prev_h = settings.get("track_height_prev", Lane.H_DEF)
        self.dnd = TkinterDnD is not None

        root.title(APP_NAME)
        sh = root.winfo_screenheight()
        root.geometry(f"1280x{max(700, min(1000, sh - 90))}+40+20")
        root.minsize(980, 680)
        ico = engine.BASE_DIR / "assets" / "icon.ico"
        if sys.platform == "win32" and ico.exists():
            try:
                root.iconbitmap(str(ico))
            except Exception:
                pass
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        self._build_ui()

        if not self.player.open_stream():
            self.status.configure(text="No audio output found – playback is off, export still works")

        if self.dnd:
            try:
                root.drop_target_register(DND_FILES)
                root.dnd_bind("<<Drop>>", self._on_drop)
                root.dnd_bind("<<DropEnter>>", lambda e: (self._drop_highlight(True), e.action)[1])
                root.dnd_bind("<<DropLeave>>", lambda e: (self._drop_highlight(False), e.action)[1])
                self.dnd = True
            except Exception:
                self.dnd = False
                traceback.print_exc()
            self._draw_drop()
        root.bind_all("<space>", self._on_space)
        for k in ("s", "S"):
            root.bind_all(f"<KeyPress-{k}>", lambda e: self._selected_key(Lane.toggle_solo))
        for k in ("m", "M"):
            root.bind_all(f"<KeyPress-{k}>", lambda e: self._selected_key(Lane.toggle_mute))
        root.bind_all("<Home>", lambda e: None if self._typing() else self.seek(0))
        root.bind_all("<Control-s>", lambda e: (self.save_project(), "break")[1])
        root.bind_all("<Control-S>", lambda e: (self.save_project(save_as=True), "break")[1])
        root.bind_all("<Button-1>", self._click_anywhere, add="+")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_all()
        root.after(40, self._tick)

    # ----- transport -----
    def toggle_play(self):
        if self.player.stream is None:
            self.flash(self.player.device_error and "No audio output device found."
                       or "No audio output device found.")
            return
        self.player.toggle()

    def toggle_loop(self):
        self.player.loop = not self.player.loop
        self._style_loop()
        self.refresh_region()

    def on_fade(self, v):
        self.player.loop_fade = round(float(v), 1)
        self.fade_val.configure(text=f"{self.player.loop_fade:.1f} s")
        self.refresh_region()

    def seek(self, frac):
        self.player.seek(frac)
        self._update_positions()

    def _typing(self):
        w = self.root.focus_get()
        return isinstance(w, tk.Entry)

    def _on_space(self, e):
        if self._typing():
            return None
        self.toggle_play()
        return "break"

    # ----- loop -----
    def _tick(self):
        try:
            self._collect_garbage()
            self._handle_events()
            self._split_button_tick()
            if self.player.render_busy > 0:
                self._update_busy()  # keeps the spinner turning
            self._update_positions()
            self.fader.set_levels(self.player.take_meter())
            self.fader.show_clip(self.player.clip)
            self._title_n = getattr(self, "_title_n", 0) + 1
            if self._title_n % 15 == 0 and self.project_path:
                self._update_title()
            playing = self.player.playing
            if playing != getattr(self, "_shown_playing", None):
                self._shown_playing = playing
                self.play_btn.configure(image=icon("pause" if playing else "play", ACCENT_TXT, 28))
        except Exception:
            traceback.print_exc()
        self.root.after(33, self._tick)

    def _collect_garbage(self):
        """Python's garbage collector runs only here, on the main thread (run_gui turns the automatic
        one off). Freed Tk objects (fonts, images) call into Tk; when the collector happened to run on a
        background thread, that call waited for the main thread while the main thread waited for the
        thread to start - and the app froze."""
        if gc.get_count()[0] < gc.get_threshold()[0]:
            return
        self._gc_n = getattr(self, "_gc_n", 0) + 1
        gc.collect(2 if self._gc_n % 100 == 0 else 1 if self._gc_n % 10 == 0 else 0)

    def _update_positions(self):
        frac = self.player.position()
        n = self.player.length()
        for lane in self.lanes:
            lane.update_playhead(frac)
        sr = engine.SR
        self.time_lbl.configure(text=f"{fmt_time(frac * n / sr)} / {fmt_time(n / sr)}")
        if getattr(self, "_ruler_len", None) != (n, self.player.region, self.player.loop, self.player.loop_fade):
            self.draw_ruler()

    def _handle_events(self):
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                return
            kind = ev[0]
            if kind == "loaded":
                self.loading -= 1
                self._draw_drop()
                self._add_track(ev[1], ev[2], ev[3])
                if self.loading == 0:
                    self._finish_restore()
            elif kind == "load_error":
                self.loading -= 1
                self._draw_drop()
                self.flash(f"Couldn't open {Path(ev[1]).name}")
                if self.loading == 0:
                    self._finish_restore()
                print("load error", ev[1], ev[2])
            elif kind == "render":
                self._update_busy()
                self.draw_ruler()
            elif kind == "analysed":
                if ev[1] == self._analysis_gen:
                    self.analysing = False
                    found = self.tuning_found(ev[2])
                    self.auto_result = ev[2] if found else None   # turning Auto 440 on again retries
                    if self.auto and not found and self.lanes:
                        self.auto_var.set(False)       # nothing to go on: back to the user's own value
                        self.on_auto()
                        self.show_alert("Auto 440", "Auto 440 couldn't detect the tuning of this track, "
                                                    "so it has been turned off. You can still fine-tune "
                                                    "by hand with the slider.")
                    elif self.auto:
                        self.fine_slider.configure(state="normal")
                        self.fine_slider.set(self.current_cents())
                    self._style_fine()
                    self._live(0)
            elif kind == "export_done" and self.export_dialog:
                self.export_dialog.done(ev[1], ev[2])
            elif kind == "export_progress" and self.export_dialog:
                self.export_dialog.progress(ev[1])
            elif kind == "yt_info" and ev[1] is self.split_pop:
                if isinstance(ev[3], dict) and ev[3].get("error") and ev[3].get("url"):
                    self.note_yt_failure()      # YouTube couldn't read the link
                self.split_pop.got_info(ev[2], ev[3])
            elif kind == "split_stage" and ev[1] is self.split_job:
                ev[1].progress[ev[2]] = ev[3]
                self._split_refresh()
            elif kind == "open_paths":          # NiSH Player was started again (e.g. a .nish double-click)
                self.bring_to_front()
                if ev[1]:
                    self.open_paths(ev[1])
            elif kind == "settings_refresh":
                if self.settings_pop is not None and self.settings_pop.frame.winfo_exists():
                    self.settings_pop.refresh()
            elif kind == "split_done" and ev[1] is self.split_job:
                self._split_finished(ev[1], ev[2], ev[3])

    # ----- Split song -----
    def open_split(self):
        import split_ui
        if self.split_pop is None or not self.split_pop.frame.winfo_exists():
            self.split_pop = split_ui.SplitPopover(self, self.split_btn)
        elif self.split_pop.is_open():
            self.split_pop.close()
            return
        else:
            self.split_pop.show("work" if self.split_job else "setup")
            self.split_pop.place()
        self.split_pop.url.focus_set()
        self.root.bind("<Escape>", lambda e: self.split_pop.close() if self.split_pop and self.split_pop.is_open() else None)

    def _split_refresh(self):
        if self.split_pop and self.split_pop.is_open() and self.split_pop.work.winfo_ismapped():
            self.split_pop.refresh_work()

    def _split_finished(self, job, result, error):
        job.running = False
        job.result, job.error = result, error
        if error and error != "Cancelled." and splitter_is_url(job.source) \
                and job.progress.get("download", 0) < 1:
            self.note_yt_failure()          # YouTube extraction failed (not the split)
        if result and job.opts["workspace"]:
            job.progress["load"] = 1.0
            if result.get("project") and not self.lanes and not self.loading:
                # an empty workspace becomes the new project (so Ctrl+S saves into it)
                self.project_path = None
                self._restore = {"tracks": {}, "loop": {}, "path": str(result["project"])}
            self.add_files([p for p, _ in result["load"]], names={str(p): lbl for p, lbl in result["load"]})
        if result:
            self._split_done_until = self.root.winfo_toplevel().tk.call("clock", "milliseconds") + 5000
        self._split_refresh()

    def _split_button_tick(self):
        """While a split runs, the header button becomes a spinner with the current step."""
        job = self.split_job
        now = int(self.root.tk.call("clock", "milliseconds"))
        if job and job.running:
            frame = (now // 90) % 12
            state = ("spin", frame, job.short_status())
        elif job and job.result and now < getattr(self, "_split_done_until", 0):
            state = ("done",)
        else:
            state = ("idle",)
        if state == self._split_status:
            return
        self._split_status = state
        if state[0] == "spin":
            self.split_btn.configure(image=icon(f"spin{state[1]}", ACCENT_SOFT, 18), text=state[2],
                                  border_color=ACCENT, text_color=ACCENT_SOFT)
        elif state[0] == "done":
            self.split_btn.configure(image=icon("check", GREEN, 16), text="Done", border_color=GREEN_BORDER,
                                  text_color=GREEN_TXT)
        else:
            self.split_btn.configure(image=icon("split", ACCENT_SOFT, 18), text="Split",
                                  border_color=BORDER2, text_color=TEXT2)

    def flash(self, msg, ms=4000):
        self.status.configure(text=msg, text_color=AMBER_TXT)
        self.root.after(ms, lambda: self.status.configure(
            text="" if self.player.stream is not None else "No audio output found – playback is off, export still works"))

    # ----- export -----
    def open_export(self):
        if not self.lanes:
            self.flash("Add some audio first.")
            return
        if self.export_dialog and self.export_dialog.win.winfo_exists():
            self.export_dialog.win.focus()
            return
        self.export_dialog = ExportDialog(self)

    def close(self):
        if not self.confirm_discard():
            return
        self.player.close()
        self.root.destroy()

    def bring_to_front(self):
        r = self.root
        try:
            r.deiconify()
            r.lift()
            r.attributes("-topmost", True)
            r.after(300, lambda: r.attributes("-topmost", False))
            r.focus_force()
        except Exception:
            pass

    # ----- settings / updates -----
    def open_settings(self):
        import settings_menu
        if self.settings_pop is not None and self.settings_pop.frame.winfo_exists():
            if self.settings_pop.is_open():
                self.settings_pop.close()
            else:
                self.settings_pop.refresh()
                self.settings_pop.place()
            return
        self.settings_pop = settings_menu.SettingsMenu(self, self.cog_btn)

    def _style_cog(self):
        """The cogwheel turns amber when YouTube keeps failing today (an update may help)."""
        warn = settings.suggest_update()
        self.cog_btn.configure(image=icon("cog", AMBER if warn else TEXT2, 18),
                               border_color=AMBER_BORDER if warn else BORDER2)

    def note_yt_failure(self):
        settings.note_yt_failure()
        self._style_cog()
        if self.settings_pop is not None and self.settings_pop.frame.winfo_exists():
            self.settings_pop.refresh()

    def install_update(self, stage):
        try:
            updater.install(stage, restart=True)
        except Exception as e:
            traceback.print_exc()
            if self.settings_pop:
                self.settings_pop.state, self.settings_pop.error = "error", f"Couldn't start the update: {e}"
                self.settings_pop.refresh()
            return
        self.close()




# ---------------------------------------------------------------------------

def make_root():
    ctk.set_appearance_mode("dark")
    if TkinterDnD is not None:
        class Root(ctk.CTk, TkinterDnD.DnDWrapper):
            def __init__(self):
                super().__init__()
                self.TkdndVersion = TkinterDnD._require(self)
        try:
            return Root()
        except Exception:
            traceback.print_exc()
    globals()["TkinterDnD"] = None
    return ctk.CTk()


def run_gui(files=(), smoketest_dir=None):
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens and our own taskbar icon
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nish.player")
        except Exception:
            pass
    theme.set_mode(settings.get("theme", "dark"))     # dark unless the user picked light
    gc.disable()        # garbage is collected on the main thread only (App._collect_garbage)
    root = make_root()
    app = App(root)
    if files:
        root.after(200, lambda: app.open_paths(files))
    srv = None
    if not smoketest_dir:
        import instance
        srv = instance.serve(lambda paths: app.events.put(("open_paths", paths)))
        threading.Thread(target=lambda: _quiet(instance.register_file_type), daemon=True).start()
    if smoketest_dir:
        import smoketest
        root.after(600, lambda: smoketest.run(app, smoketest_dir))
    root.mainloop()
    if srv is not None:
        import instance
        instance.stop(srv)
    return app


def _quiet(fn):
    try:
        fn()
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--yt-selftest":
        import smoketest
        sys.exit(smoketest.yt_selftest(sys.argv[2], sys.argv[3]))
    if len(sys.argv) >= 3 and sys.argv[1] == "--gui-smoketest":
        app = run_gui(smoketest_dir=sys.argv[2])
        sys.exit(getattr(app, "smoketest_exit", 1))
    try:
        files = [a for a in sys.argv[1:] if not a.startswith("--")]
        import instance
        if instance.hand_off(files):       # already running: it opens the files, this start ends here
            sys.exit(0)
        run_gui(files=files)
    except Exception:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc())
        try:
            messagebox.showerror(APP_NAME, "Something went wrong. Details are in:\n" + str(LOG_FILE))
        except Exception:
            pass
        raise
