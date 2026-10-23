"""The Export… dialog."""
import math
import subprocess
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

import engine
import settings
from theme import *  # noqa: F401,F403


# ---------------------------------------------------------------------------
# Export dialog
# ---------------------------------------------------------------------------

class ExportDialog:
    def __init__(self, app):
        self.app = app
        self.busy = False
        self.written = []
        win = self.win = ctk.CTkToplevel(app.root)
        win.title("Export")
        win.configure(fg_color=WAVE)
        win.resizable(False, False)
        win.transient(app.root)
        win.geometry("+%d+%d" % (app.root.winfo_rootx() + 360, app.root.winfo_rooty() + 90))

        lanes = app.lanes
        self.main = app.main_folder()        # exports go to the song's main folder when there is one
        self.folder = self.main or settings.export_folder()
        gains = app.player.gains()
        self.tags = engine.tags(app.speed, app.semis, app.current_cents(), app.auto)
        self.region = app.player.active_region()
        if self.region:
            self.tags.append(engine.region_tag(*self.region, app.player.speed).lstrip("_"))

        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(18, 0))
        ctk.CTkLabel(body, text="Export", font=font(18, "bold"), text_color=TEXT).pack(anchor="w")

        self._section(body, "WHAT TO EXPORT")
        self.mode = tk.StringVar(value="mix")
        for value, title, sub in (("mix", "Full mix", "One file – all changes applied"),
                                  ("each", "Each track separately",
                                   "One file per track, same speed and pitch.")):
            f = ctk.CTkFrame(body, fg_color=POPOVER, border_color=BORDER2, border_width=1, corner_radius=10)
            f.pack(fill="x", pady=4)
            rb = ctk.CTkRadioButton(f, text=title, value=value, variable=self.mode, font=font(13, "bold"),
                                    text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                    border_color=CONTROL, command=self.refresh)
            rb.pack(anchor="w", padx=14, pady=(8, 0))
            ctk.CTkLabel(f, text=sub, font=font(12), text_color=MUTED).pack(anchor="w", padx=44, pady=(0, 8))
            if len(lanes) == 1 and value == "each":
                rb.configure(state="disabled")
        if self.region:    # loop is on: only the marked area is exported (amber, right under the choice)
            sp = app.player.speed
            span = f"{fmt_time(self.region[0] / engine.SR / sp)} – {fmt_time(self.region[1] / engine.SR / sp)}"
            note = ctk.CTkFrame(body, fg_color=AMBER_BADGE, border_color=AMBER_BORDER, border_width=1,
                                corner_radius=8)
            note.pack(fill="x", pady=(6, 0))
            f = app.player.loop_fade
            fades = "with no fades" if f <= 0 else f"with {f:g}-second fades in and out"
            self.loop_note = ctk.CTkLabel(note, text=f"  Loop is on – only the marked area ({span}) will be "
                                          f"exported, {fades}.", font=font(12), text_color=AMBER_TXT,
                                          wraplength=460, justify="left", image=icon("loop", AMBER, 15),
                                          compound="left")
            self.loop_note.pack(anchor="w", padx=12, pady=8)

        self._section(body, "FORMAT")
        self.fmt = ctk.CTkSegmentedButton(body, values=["WAV", "FLAC", "MP3 320"], height=40, font=font(13),
                                          selected_color=ACCENT_SEL, selected_hover_color=ACCENT_SEL_HOVER,
                                          unselected_color=BTN, unselected_hover_color=BTN_HOVER,
                                          text_color=TEXT, command=lambda v: self.refresh())
        self.fmt.set("WAV")
        self.fmt.pack(fill="x")

        self._section(body, "INCLUDED CHANGES")
        chips = ctk.CTkFrame(body, fg_color="transparent")
        chips.pack(fill="x")
        items = []
        if abs(app.speed - 1) > 1e-6:
            items.append((f"Speed {app.speed:.2f}×", True))
        if app.semis:
            items.append((f"Pitch {engine.fmt_semitones(app.semis)} semitones".replace("-", "−"), True))
        if app.auto and app.current_cents():
            items.append(("Auto 440", "amber"))
        elif not app.auto and round(app.manual_cents):
            items.append((f"Fine {app.manual_cents:+.0f} ct".replace("-", "−"), True))
        autos = [l.track.label for l, g in zip(lanes, gains) if g > 0 and l.track.automation_active()]
        if autos:
            items.append(("Automation: " + ", ".join(autos), "green"))
        for lane, g in zip(lanes, gains):
            if lane.track.mute:
                items.append((f"{lane.track.label} muted", False))
            elif g <= 0:
                items.append((f"{lane.track.label} not soloed", False))
        if fader_db(app.fader.pos) != 0:
            db = fader_db(app.fader.pos)
            items.append(("Master −∞ dB" if db == -math.inf else f"Master {db:+.1f} dB".replace("-", "−"), False))
        if not items:
            items.append(("No changes – a plain mix", False))
        for text, strong in items:
            bg, fg = ((AMBER_BADGE, AMBER) if strong == "amber" else (GREEN_BG, GREEN_TXT) if strong == "green"
                      else (CHIP_ACCENT, CHIP_ACCENT_TXT) if strong else (CHIP, BTN_TXT))
            ctk.CTkLabel(chips, text=f"  {text}  ", font=font(12, mono=True), corner_radius=12, height=26,
                         fg_color=bg, text_color=fg).pack(side="left", padx=(0, 6))
        self.name_title = self._section(body, "FILE NAME")
        self.name_var = tk.StringVar(value=engine.safe_filename(
            "_".join([engine.song_name([l.track.path for l in lanes]), "mix"] + self.tags)))
        self.name_entry = ctk.CTkEntry(body, textvariable=self.name_var, height=40, font=font(13, mono=True),
                                       fg_color=FIELD, border_color=BORDER2, text_color=TEXT)
        self.name_entry.pack(fill="x")
        self.name_hint = ctk.CTkLabel(body, text="", font=font(12), text_color=MUTED, anchor="w",
                                      wraplength=470, justify="left")

        loc = ctk.CTkFrame(body, fg_color="transparent")
        loc.pack(fill="x", pady=(12, 0))
        self.loc_lbl = ctk.CTkLabel(loc, text="", font=font(12), text_color=MUTED, anchor="w")
        self.loc_lbl.pack(side="left", fill="x", expand=True)
        ToolButton(loc, "Change…", self.change_folder, height=32).pack(side="right")

        self.prog = ctk.CTkProgressBar(body, height=6, progress_color=ACCENT, fg_color=BORDER2)
        self.prog.set(0)
        self.msg = ctk.CTkLabel(body, text="", font=font(12), text_color=MUTED, anchor="w",
                                wraplength=470, justify="left", compound="left")

        ctk.CTkFrame(win, fg_color=BORDER, height=1, corner_radius=0).pack(fill="x", pady=(18, 0))
        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=24, pady=14)
        self.go_btn = ToolButton(btns, "Export", self.start, height=44, width=110, primary=True)
        self.go_btn.pack(side="right")
        self.cancel_btn = ToolButton(btns, "Cancel", self.close, height=44, width=100)
        self.cancel_btn.pack(side="right", padx=10)
        self.show_btn = ToolButton(btns, "Show in folder", self.show_folder, height=44)
        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda e: self.close())
        self.refresh()
        win.after(150, lambda: (win.grab_set() if win.winfo_exists() else None))

    def _section(self, parent, text):
        lbl = ctk.CTkLabel(parent, text=text, font=font(11), text_color=MUTED)
        lbl.pack(anchor="w", pady=(16, 6))
        return lbl

    def fmt_key(self):
        return "MP3" if self.fmt.get().startswith("MP3") else self.fmt.get()

    def refresh(self):
        ext = {"WAV": ".wav", "FLAC": ".flac", "MP3": ".mp3"}[self.fmt_key()]
        if self.mode.get() == "mix":
            self.name_title.configure(text="FILE NAME")
            self.name_hint.pack_forget()
            self.name_entry.pack(fill="x", after=self.name_title)
            self.loc_lbl.configure(text=f"Saves to: {self._short(self.folder)}{self._where()}   ({ext})")
        else:
            self.name_entry.pack_forget()
            self.name_title.configure(text="FILE NAMES")
            first = Path(self.app.lanes[0].track.path).stem
            self.name_hint.configure(text="Named after the original files, e.g. "
                                          + engine.safe_filename("_".join([first] + self.tags)) + ext)
            self.name_hint.pack(fill="x", after=self.name_title)
            self.loc_lbl.configure(text=f"Saves to: {self._short(self.folder)}{self._where()}")

    def _where(self):
        return "   (song folder)" if self.main and self.folder == self.main else ""

    @staticmethod
    def _short(path, n=46):
        return path if len(path) <= n else "…" + path[-(n - 1):]

    def change_folder(self):
        d = filedialog.askdirectory(parent=self.win, initialdir=self.folder, title="Export to folder")
        if d:
            self.folder = d
            if not self.main:
                settings.set_export_folder(d)   # becomes the default export folder
            self.refresh()

    def start(self):
        if self.busy:
            return
        app = self.app
        mode, fmt = self.mode.get(), self.fmt_key()
        ext = {"WAV": ".wav", "FLAC": ".flac", "MP3": ".mp3"}[fmt]
        if mode == "mix":
            name = engine.safe_filename(self.name_var.get().strip() or "mix")
            if name.lower().endswith(ext):
                name = name[: -len(ext)]
            dest = engine.unique_path(Path(self.folder) / (name + ext))
        else:
            dest = Path(self.folder)
        tracks = [l.track for l in app.lanes]
        gains = app.player.gains()
        master = app.player.master
        speed, semis, cents = app.stretch_params()
        self.busy = True
        self.go_btn.configure(state="disabled", text="Exporting…")
        self.prog.pack(fill="x", pady=(14, 0))
        self.msg.pack(fill="x", pady=(6, 0))
        self.msg.configure(text="Rendering at full quality…", text_color=MUTED)

        def work():
            try:
                w = engine.export(tracks, gains, master, speed, semis, mode, fmt, dest,
                                  progress=lambda f: app.events.put(("export_progress", f)),
                                  name_tags=self.tags, region=self.region, fade=app.player.loop_fade,
                                  cents=cents)
                app.events.put(("export_done", True, w))
            except Exception as e:
                traceback.print_exc()
                app.events.put(("export_done", False, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def progress(self, f):
        self.prog.set(f)

    def done(self, ok, result):
        self.busy = False
        self.go_btn.configure(state="normal", text="Export")
        if ok:
            self.written = result
            self.prog.set(1)
            names = ", ".join(Path(p).name for p in result[:3]) + (" …" if len(result) > 3 else "")
            self.msg.configure(text=f"  Saved {names}", text_color=GREEN_TXT, image=icon("check", GREEN, 13))
            self.cancel_btn.configure(text="Close")
            self.show_btn.pack(side="left")
        else:
            self.msg.configure(text=f"Export failed: {result}", text_color=AMBER_TXT)
            no_image(self.msg)

    def show_folder(self):
        target = Path(self.written[0]) if self.written else Path(self.folder)
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target.parent)])
        except Exception:
            traceback.print_exc()

    def close(self):
        if self.busy:
            return
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()
        self.app.export_dialog = None
