"""Speed, pitch, fine tuning and Auto 440 in the main window."""
import threading
import traceback

import customtkinter as ctk

import engine
from theme import *  # noqa: F401,F403


class SpeedPitchMixin:
    """Speed / pitch / tuning (part of App)."""

    # ----- speed / pitch / tuning -----
    def current_cents(self):
        if self.auto:
            return self.auto_result[0] if self.auto_result else 0.0
        return self.manual_cents

    @staticmethod
    def tuning_found(res):
        return bool(res and res[1] is not None and res[2] >= 0.12)

    def stretch_params(self):
        """(speed, semitones, cents) for the player and export: speed and semitones go through
        Rubber Band, the fine-tuning cents through varispeed (no tempo compensation)."""
        return self.speed, self.semis, self.current_cents()

    def on_speed(self, v):
        self.speed = round(float(v), 2)
        self.speed_val.configure(text=f"{self.speed:.2f}×")
        self._live()

    def on_pitch(self, v):
        self.semis = int(round(float(v)))
        self.pitch_val.configure(text=f"{engine.fmt_semitones(self.semis)} semitones".replace("-", "−")
                                 if self.semis else "0 semitones")
        self._live()

    def on_fine(self, v):
        if self.auto:
            return
        self.manual_cents = round(float(v))
        self._style_fine()
        self._live()

    def on_auto(self):
        self.auto = bool(self.auto_var.get())
        if self.auto:
            if self.lanes and self.auto_result is None:
                self.start_analysis()
            self.fine_slider.set(self.current_cents())
        else:
            self.fine_slider.configure(state="normal")
            self.fine_slider.set(self.manual_cents)
        self._style_fine()
        self._live(0)

    def show_alert(self, title, text):
        """A small modal message box in the app's own style."""
        if self.alert_win is not None and self.alert_win.winfo_exists():
            self.alert_win.destroy()
        win = self.alert_win = ctk.CTkToplevel(self.root)
        win.title(title)
        win.configure(fg_color=HEADER)
        win.resizable(False, False)
        win.transient(self.root)
        win.geometry("+%d+%d" % (self.root.winfo_rootx() + 420, self.root.winfo_rooty() + 260))
        ctk.CTkLabel(win, text="  " + title, font=font(15, "bold"), text_color=TEXT, image=icon("warn", AMBER, 16),
                     compound="left").pack(anchor="w", padx=24, pady=(20, 6))
        ctk.CTkLabel(win, text=text, font=font(13), text_color=SOFT, wraplength=380, justify="left",
                     anchor="w").pack(fill="x", padx=24)
        ok = ToolButton(win, "OK", win.destroy, height=36, width=90, primary=True)
        ok.pack(anchor="e", padx=24, pady=(16, 18))
        win.bind("<Return>", lambda e: win.destroy())
        win.bind("<Escape>", lambda e: win.destroy())
        win.after(100, lambda: (win.grab_set(), ok.focus_set()) if win.winfo_exists() else None)

    def start_analysis(self):
        self.auto_result = None
        if not self.lanes:
            self._style_fine()
            return
        self.analysing = True
        self._analysis_gen += 1
        gen = self._analysis_gen
        tracks = [l.track for l in self.lanes]
        self._style_fine()

        def work():
            try:
                res = engine.analyse_tuning(tracks)
            except Exception:
                traceback.print_exc()
                res = (0.0, None, 0.0)
            self.events.put(("analysed", gen, res))

        threading.Thread(target=work, daemon=True).start()

    def reset_stretch(self):
        self.speed_slider.set(1.0)
        self.pitch_slider.set(0)
        self.on_speed(1.0)
        self.on_pitch(0)
        if not self.auto:
            self.fine_slider.set(0)
            self.on_fine(0)

    def _live(self, delay=350):
        """Heard at once through the real-time stretcher; the high-quality version
        renders once the slider has been still for a moment."""
        self.player.set_live(*self.stretch_params())
        self._schedule_stretch(delay)

    def _schedule_stretch(self, delay=350):
        if self._stretch_job:
            self.root.after_cancel(self._stretch_job)
        self._stretch_job = self.root.after(delay, self.apply_stretch)

    def apply_stretch(self):
        self._stretch_job = None
        self.player.set_stretch(*self.stretch_params())
        self._update_busy()

    def _update_busy(self):
        if self.player.render_busy > 0:
            frame = (int(self.root.tk.call("clock", "milliseconds")) // 90) % 12
            self.busy_lbl.configure(text="  Polishing…", text_color=ACCENT_SOFT,
                                    image=icon(f"spin{frame}", ACCENT_SOFT, 14))
        elif self.player.render_error:
            self.busy_lbl.configure(text="Couldn't apply speed & pitch – see the log", text_color=AMBER_TXT)
            no_image(self.busy_lbl)
        else:
            self.busy_lbl.configure(text="Tip: Ctrl+click a slider to reset it", text_color=DIM)
            no_image(self.busy_lbl)
