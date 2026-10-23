"""Small custom widgets: the master fader with meters, the Auto 440 switch, and Ctrl+click-to-reset for sliders."""
import math
import tkinter as tk

import customtkinter as ctk

import theme
from theme import *  # noqa: F401,F403


# ---------------------------------------------------------------------------
# Master fader with L/R meters and a latching clip light
# ---------------------------------------------------------------------------

class MasterFader:
    W, H = 132, 164
    TOP, BOTTOM = 10, 146
    FX = 66     # fader centre
    MX = 100    # meters

    def __init__(self, app, parent):
        self.app = app
        self.pos = db_pos(0.0)
        self.levels = [0.0, 0.0]
        self.card = ctk.CTkFrame(parent, fg_color=POPOVER, border_color=BORDER2, border_width=1,
                                 corner_radius=10)
        # Title centred over the fader; level and the clip light underneath
        ctk.CTkLabel(self.card, text="Master", font=font(14, "bold"), text_color=TEXT, height=20).pack(
            pady=(12, 4))
        self.canvas = tk.Canvas(self.card, width=self.W, height=self.H, bg=POPOVER,
                                highlightthickness=0, cursor="sb_v_double_arrow")
        self.canvas.pack(padx=8)
        self.db_lbl = ctk.CTkLabel(self.card, text="0.0 dB", font=font(13, mono=True),
                                   text_color=ACCENT_SOFT, height=20)
        self.db_lbl.pack(pady=(2, 6))
        self.clip_btn = ctk.CTkButton(self.card, text="CLIP", compound="left", width=62, height=26,
                                      corner_radius=6, font=font(10, "bold", True), fg_color="transparent",
                                      border_width=1, command=self.reset_clip)
        self.clip_btn.pack(pady=(0, 12))
        self.clip_shown = None
        c = self.canvas
        for e in ("<Button-1>", "<B1-Motion>"):
            c.bind(e, self._drag)
        c.bind("<Double-Button-1>", lambda e: self.set_pos(db_pos(0.0)))
        c.bind("<Control-Button-1>", lambda e: (self.set_pos(db_pos(0.0)), "break")[1])
        c.bind("<Control-B1-Motion>", lambda e: "break")
        c.bind("<MouseWheel>", lambda e: self.set_pos(self.pos + (0.02 if e.delta > 0 else -0.02)))
        c.bind("<Button-4>", lambda e: self.set_pos(self.pos + 0.02))
        c.bind("<Button-5>", lambda e: self.set_pos(self.pos - 0.02))
        self._draw_static()
        self.set_pos(self.pos)
        self.show_clip(False)

    def y_of(self, pos):
        return self.BOTTOM - pos * (self.BOTTOM - self.TOP)

    def _draw_static(self):
        c = self.canvas
        for p, txt in zip((1.0, 0.8, 0.6, 0.4, 0.2, 0.0), ("+6", "0", "−6", "−12", "−24", "−∞")):
            y = self.y_of(p)
            c.create_text(34, y, text=txt, anchor="e", fill=DIM, font=(MONO, 9))
            c.create_line(38, y, 44, y, fill=BORDER2)
        c.create_rectangle(self.FX - 7, self.TOP, self.FX + 7, self.BOTTOM, fill=SLOT,
                           outline=BORDER2)
        self.fill = c.create_rectangle(self.FX - 6, self.TOP, self.FX + 6, self.BOTTOM, fill=ACCENT,
                                       width=0)
        self.cap = c.create_rectangle(0, 0, 0, 0, fill=FADER_CAP, outline=FADER_CAP_EDGE)
        self.cap_line = c.create_line(0, 0, 0, 0, fill=FADER_CAP_MARK, width=2)
        self.meters = []
        for i in range(2):
            x = self.MX + i * 10
            c.create_rectangle(x, self.TOP, x + 6, self.BOTTOM, fill=SLOT, width=0)
            segs = [c.create_rectangle(x, self.BOTTOM, x + 6, self.BOTTOM, fill=col, width=0)
                    for col in (GREEN, AMBER, RED)]
            self.meters.append(segs)
        c.create_text(self.MX + 3, self.BOTTOM + 9, text="L", fill=DIM, font=(MONO, 8))
        c.create_text(self.MX + 13, self.BOTTOM + 9, text="R", fill=DIM, font=(MONO, 8))

    def _drag(self, e):
        self.set_pos((self.BOTTOM - e.y) / (self.BOTTOM - self.TOP))

    def set_pos(self, pos):
        self.pos = max(0.0, min(1.0, pos))
        db = fader_db(self.pos)
        self.app.player.master = 0.0 if db == -math.inf else 10 ** (db / 20)
        y = self.y_of(self.pos)
        c = self.canvas
        c.coords(self.fill, self.FX - 6, y, self.FX + 6, self.BOTTOM)
        c.coords(self.cap, self.FX - 22, y - 12, self.FX + 22, y + 12)
        c.coords(self.cap_line, self.FX - 15, y, self.FX + 15, y)
        self.db_lbl.configure(text="−∞ dB" if db == -math.inf else f"{db:+.1f} dB".replace("-", "−"))

    def set_levels(self, peaks):
        for i in range(2):
            v = float(peaks[i]) if i < len(peaks) else 0.0
            self.levels[i] = max(v, self.levels[i] * 0.82)
            db = 20 * math.log10(self.levels[i]) if self.levels[i] > 1e-5 else -100
            top = db_pos(db)
            bounds = (0.0, db_pos(-6), db_pos(0), 1.0)
            for seg, lo, hi in zip(self.meters[i], bounds, bounds[1:]):
                if top <= lo:
                    self.canvas.coords(seg, 0, 0, 0, 0)
                else:
                    x = self.MX + i * 10
                    self.canvas.coords(seg, x, self.y_of(min(top, hi)), x + 6, self.y_of(lo))

    def show_clip(self, on):
        if on == self.clip_shown:
            return
        self.clip_shown = on
        if on:
            self.clip_btn.configure(text_color=RED_TXT, border_color=RED_BORDER, fg_color=RED_BG,
                                    hover_color=RED_BG, image=icon("dot", RED, 10))
        else:
            self.clip_btn.configure(text_color=DIM, border_color=BORDER2, fg_color="transparent",
                                    hover_color=BTN_HOVER, image=icon("dot", CLIP_OFF, 10))

    def reset_clip(self):
        self.app.player.clip = False
        self.show_clip(False)


class ForkSwitch(ctk.CTkFrame):
    """The Auto 440 switch: a small switch whose knob carries a tuning fork, then its label.
    Follows `variable`; clicking toggles it and calls `command`."""
    W, H, K = 34, 18, 14

    def __init__(self, parent, text, variable, command):
        super().__init__(parent, fg_color="transparent")
        self.var, self.command = variable, command
        bg = parent.cget("fg_color")
        if isinstance(bg, (tuple, list)):
            bg = bg[0]
        self.c = tk.Canvas(self, width=self.W, height=self.H, highlightthickness=0, bd=0, cursor="hand2",
                           bg=bg if isinstance(bg, str) and bg.startswith("#") else CARD)
        self.c.pack(side="left")
        self.lbl = ctk.CTkLabel(self, text=text, font=font(12), text_color=WARN, cursor="hand2")
        self.lbl.pack(side="left", padx=(6, 0))
        for w in (self.c, self.lbl):
            w.bind("<Button-1>", lambda e: self.toggle())
        self._trace = variable.trace_add("write", lambda *a: self.draw())
        self.bind("<Destroy>", lambda e: self._untrace(), add="+")
        self.draw()

    def _untrace(self):
        try:
            self.var.trace_remove("write", self._trace)
        except Exception:
            pass

    def set_bg(self, color):
        self.c.configure(bg=color)

    def toggle(self):
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def draw(self):
        if not self.c.winfo_exists():
            return
        c, W, H, K = self.c, self.W, self.H, self.K
        on = bool(self.var.get())
        c.delete("all")
        track = WARN_TRACK if on else SWITCH_OFF
        c.create_oval(0, 0, H, H, fill=track, outline="")
        c.create_oval(W - H, 0, W, H, fill=track, outline="")
        c.create_rectangle(H / 2, 0, W - H / 2, H, fill=track, outline="")
        x = W - 2 - K if on else 2
        c.create_oval(x, 2, x + K, 2 + K, fill=WARN_KNOB, outline="")
        fork = "#ffffff" if theme.MODE == "light" else "#8a5d00"
        self._img = theme.photo("fork", fork, 10)
        c.create_image(x + K / 2, 2 + K / 2, image=self._img)


def ctrl_reset(slider, value, handler):
    """Ctrl+click puts a slider back to its default."""
    def do(e):
        if str(slider.cget("state")) == "disabled":
            return "break"
        slider.set(value)
        handler(value)
        return "break"
    slider.bind("<Control-Button-1>", do)
    slider.bind("<Control-B1-Motion>", lambda e: "break")


class EntryHint:
    """Placeholder text for a CTkEntry that has a textvariable. (CustomTkinter only shows its own
    placeholder without one.) Shown in CustomTkinter's placeholder colour while the variable is
    empty; clicking it puts the cursor in the entry."""

    def __init__(self, entry, var, text):
        self.entry, self.var, self.inner = entry, var, entry._entry
        self.lbl = tk.Label(entry, text=text, font=self.inner.cget("font"), bd=0, padx=0, pady=0, cursor="xterm")
        self.lbl.bind("<Button-1>", lambda e: (self.inner.focus_set(), self.inner.icursor("end")))
        var.trace_add("write", lambda *a: self.update())
        self.update()

    def set(self, text):
        self.lbl.configure(text=text)

    def update(self):
        if self.var.get():
            self.lbl.place_forget()
            return
        e = self.entry
        self.lbl.configure(bg=self.inner.cget("bg"), fg=e._apply_appearance_mode(e._placeholder_text_color))
        self.lbl.place(in_=self.inner, x=1, rely=0.5, anchor="w")
