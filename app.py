"""NiSH Player: a small multitrack player with speed, pitch, Auto 440 and export."""
import math
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

APP_NAME = "NiSH Player"

import engine  # noqa: E402  (sets up PATH for the bundled ffmpeg)

LOG_FILE = engine.DATA_DIR / "log.txt"
# A windowed .exe has no console; send stray prints to a log file instead of crashing.
if sys.stdout is None or sys.stderr is None:
    _log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

import tkinter as tk  # noqa: E402
from tkinter import filedialog, messagebox  # noqa: E402

import customtkinter as ctk  # noqa: E402
import numpy as np  # noqa: E402

TkinterDnD = DND_FILES = None
if not os.environ.get("NISH_NO_DND"):
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES  # noqa: F811
    except Exception:
        TkinterDnD = None

from theme import *  # noqa: E402,F401,F403
import project  # noqa: E402
import settings  # noqa: E402
import theme  # noqa: E402
import updater  # noqa: E402


def splitter_is_url(src):
    import splitter
    return splitter.is_url(str(src or ""))


# ---------------------------------------------------------------------------
# One track lane: header (name, M/S, volume) + waveform
# ---------------------------------------------------------------------------

class Lane:
    BAR = 4  # px per waveform bar
    PAD = 8  # px above and below the automation line's range
    H_MIN, H_MAX, H_DEF, H_COMPACT = 44, 200, 92, 64   # one height for every lane; compact below 64

    def __init__(self, app, parent, track, colors):
        self.app, self.track = app, track
        self.color, self.dim = colors
        h = app.track_h
        self.compact = None
        self.frame = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=0, border_width=0)
        self.frame.grid_columnconfigure(1, weight=1)

        head = self.head = ctk.CTkFrame(self.frame, fg_color=LANE_BG, corner_radius=0, width=HEAD_W, height=h)
        head.grid(row=0, column=0, sticky="nsw")
        head.grid_propagate(False)
        head.grid_columnconfigure(2, weight=1)
        head.grid_rowconfigure(0, weight=1)
        head.grid_rowconfigure(3, weight=1)
        self.stripe = ctk.CTkFrame(head, fg_color=ACCENT, width=3, corner_radius=0)
        self.grip = ctk.CTkLabel(head, text="", image=icon("grip", GRIP, 14), width=18, cursor="fleur")
        self.grip.grid(row=0, column=0, rowspan=4, sticky="ns", padx=(6, 0))
        self.grip.bind("<Button-1>", lambda e: self.app.drag_start(self, e))
        self.grip.bind("<B1-Motion>", lambda e: self.app.drag_move(self, e))
        self.grip.bind("<ButtonRelease-1>", lambda e: self.app.drag_end(self, e))
        sep = ctk.CTkFrame(self.frame, fg_color=BORDER, width=1, height=1, corner_radius=0)
        sep.grid(row=0, column=0, sticky="nse")

        # row 1: dot, name, (compact: V, A), M, S, ×
        self.dot = ctk.CTkLabel(head, text="", image=icon("dot", self.color, 12), width=14)
        self.name_var = tk.StringVar(value=track.label)
        self.name = ctk.CTkEntry(head, textvariable=self.name_var, font=font(13, "bold"), height=28,
                                 fg_color=LANE_BG, border_width=1, border_color=LANE_BG,
                                 text_color=TEXT, corner_radius=6)
        self.name.bind("<FocusIn>", lambda e: (self.app.select(self),
                                               self.name.configure(border_color=ACCENT, fg_color=FIELD)))
        self.name.bind("<FocusOut>", lambda e: self._commit_name())
        self.name.bind("<Return>", lambda e: self.app.root.focus_set())
        self.name.bind("<Escape>", lambda e: (self.name_var.set(self.track.label), self.app.root.focus_set()))
        self.v_btn = ctk.CTkButton(head, text="V", width=30, height=28, corner_radius=6, border_width=1,
                                   font=font(12, "bold", True), command=lambda: self.app.toggle_vol_pop(self))
        self.auto_btn = ctk.CTkButton(head, text="A", width=30, height=28, corner_radius=6, border_width=1,
                                      font=font(12, "bold", True), command=self.toggle_auto)
        self.mute_btn = ctk.CTkButton(head, text="M", width=30, height=28, corner_radius=6,
                                      font=font(12, "bold", True), command=self.toggle_mute)
        self.solo_btn = ctk.CTkButton(head, text="S", width=30, height=28, corner_radius=6,
                                      font=font(12, "bold", True), command=self.toggle_solo)
        self.solo_btn.bind("<Control-Button-1>", lambda e: (self.app.solo_only(self), "break")[1])
        self.remove_btn = ctk.CTkButton(head, text="", image=icon("close", DIM, 11), width=24, height=28, corner_radius=6,
                                        fg_color="transparent", hover_color=BTN_HOVER, text_color=DIM,
                                        font=font(12), command=lambda: self.app.remove_lane(self))

        # row 2: Vol, value, slider, A (directly under S)
        volrow = self.volrow = ctk.CTkFrame(head, fg_color="transparent")
        volrow.grid_columnconfigure(2, weight=1)
        self.vol_name = ctk.CTkLabel(volrow, text="Vol", text_color=MUTED, font=font(12), width=26, height=22,
                                     anchor="w")
        self.vol_name.grid(row=0, column=0)
        self.vol_lbl = ctk.CTkLabel(volrow, text="100%", text_color=MUTED, font=font(11, mono=True),
                                    width=38, height=22, anchor="e")
        self.vol_lbl.grid(row=0, column=1, padx=(0, 4))
        self.vol = ctk.CTkSlider(volrow, from_=0, to=100, number_of_steps=100, height=16,
                                 command=self.on_volume, progress_color=self.color,
                                 button_color=KNOB, button_hover_color=KNOB_HOVER, fg_color=BORDER2)
        self.vol.set(100)
        App.ctrl_reset(self.vol, 100, self.on_volume)
        self.vol.grid(row=0, column=2, sticky="ew", padx=(0, 6))

        self.canvas = tk.Canvas(self.frame, height=h, bg=PANEL, highlightthickness=0, cursor="hand2")
        self.canvas.grid(row=0, column=1, sticky="nsew")
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Double-Button-1>", self._double)
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", lambda e: self._hide_tip())
        for w in (self.dot, volrow, self.vol_name, self.vol_lbl):
            w.bind("<Button-1>", lambda e: self.app.select(self))
        # drag the bottom edge of the header to resize all lanes
        head.bind("<Motion>", lambda e: self._edge_cursor(head, e))
        head.bind("<Button-1>", lambda e: self._edge_press(head, e) or self.app.select(self))
        head.bind("<B1-Motion>", lambda e: self.app.resize_move(e))
        head.bind("<ButtonRelease-1>", lambda e: self.app.resize_end())
        head.bind("<Double-Button-1>", lambda e: self._edge_double(head, e))
        self.selected = False
        self.line = ctk.CTkFrame(self.frame, fg_color=BORDER, height=1, corner_radius=0)
        self.line.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.bars = []
        self.played = 0
        self.silent = False
        self.playhead = None
        self._pt_drag = None       # index of the automation point being dragged
        self._resizing = False
        self.layout()
        self.refresh_buttons()

    # --- layout (normal: two rows; compact: one row) ---
    def layout(self):
        compact = self.app.track_h < self.H_COMPACT
        if compact == self.compact:
            return
        self.compact = compact
        for w in (self.dot, self.name, self.v_btn, self.auto_btn, self.mute_btn, self.solo_btn, self.remove_btn,
                  self.volrow):
            w.grid_forget()
        r = 1
        self.dot.grid(row=r, column=1, padx=(2, 4), sticky="w")
        self.name.grid(row=r, column=2, sticky="ew", padx=(0, 4))
        if compact:
            self.v_btn.grid(row=r, column=3, padx=(0, 4))
            self.auto_btn.grid(row=r, column=4, padx=(0, 4))
        self.mute_btn.grid(row=r, column=5, padx=(0, 4))
        self.solo_btn.grid(row=r, column=6, padx=(0, 4))
        self.remove_btn.grid(row=r, column=7, padx=(0, 10))
        if not compact:
            self.volrow.grid(row=2, column=1, columnspan=5, sticky="ew", padx=(4, 0), pady=(7, 0))
            self.auto_btn.grid(row=2, column=6, padx=(0, 4), pady=(7, 0))
        self.refresh_volume_row()

    def set_height(self, h):
        self.head.configure(height=h)
        self.canvas.configure(height=h)
        self.layout()

    # --- resize from the bottom edge ---
    def _near_edge(self, widget, e):
        return e.y >= widget.winfo_height() - 5

    def _edge_cursor(self, widget, e):
        widget.configure(cursor="sb_v_double_arrow" if self._near_edge(widget, e) else "")

    def _edge_press(self, widget, e):
        if self._near_edge(widget, e):
            self.app.resize_start(self, e)
            return True
        return False

    def _edge_double(self, widget, e):
        if self._near_edge(widget, e):
            self.app.set_track_height(Lane.H_DEF, save=True)

    # --- controls ---
    def _commit_name(self):
        bg = SELECTED if self.selected else LANE_BG
        self.name.configure(border_color=bg, fg_color=bg)
        text = self.name_var.get().strip()
        if not text:
            text = engine.guess_label(self.track.path)
            self.name_var.set(text)
        if text != self.track.label:
            self.track.label = text
            engine.save_label(self.track.path, text)

    def toggle_mute(self):
        self.track.mute = not self.track.mute
        self.app.refresh_lanes()

    def toggle_solo(self):
        self.track.solo = not self.track.solo
        self.app.refresh_lanes()

    def on_volume(self, v):
        self.track.volume = float(v) / 100.0
        if not self.track.auto_on:
            self.vol_lbl.configure(text=f"{int(round(v))}%")
        self.app.volume_changed(self)

    def toggle_auto(self):
        """A: volume automation. The first time, the line starts flat at the current volume.
        Off keeps the line but ignores it."""
        self.app.select(self)
        t = self.track
        if not t.auto_on and not t.auto_pts:
            dur = max(1e-3, self.app.player.source_length() / engine.SR)
            t.set_automation(True, [(0.0, t.volume), (dur, t.volume)])
        else:
            t.set_automation(not t.auto_on)
        self.refresh_buttons()
        self.refresh_volume_row()
        self.draw()
        self.app.automation_changed(self)

    def set_automation(self, on, pts):
        self.track.set_automation(on, pts)
        self.refresh_buttons()
        self.refresh_volume_row()
        self.draw()

    def refresh_volume_row(self):
        """With automation on, the volume controls dim and say Auto."""
        on = self.track.auto_on
        bg = SELECTED if self.selected else LANE_BG
        dimc = lambda c: blend(c, bg, 0.55)
        self.vol_name.configure(text_color=dimc(MUTED) if on else MUTED)
        self.vol_lbl.configure(text="Auto" if on else f"{int(round(self.track.volume * 100))}%",
                               text_color=dimc(MUTED) if on else MUTED)
        self.vol.configure(state="disabled" if on else "normal",
                           progress_color=dimc(self.color) if on else self.color,
                           button_color=dimc(KNOB) if on else KNOB, fg_color=dimc(BORDER2) if on else BORDER2)
        self.refresh_v()

    def refresh_v(self):
        pop = self.app.vol_pop
        open_ = bool(pop and pop.lane is self and pop.frame.winfo_exists())
        bg = SELECTED if self.selected else LANE_BG
        if open_:
            self.v_btn.configure(fg_color=ACCENT_TINT, border_color=ACCENT, text_color=ACCENT_TXT,
                                 hover_color=ACCENT_TINT)
        else:
            fg = blend(SOFT, bg, 0.55) if self.track.auto_on else SOFT
            self.v_btn.configure(fg_color=BTN, border_color=BORDER2, text_color=fg, hover_color=BTN_HOVER)

    def set_selected(self, on):
        if on == self.selected:
            return
        self.selected = on
        bg = SELECTED if on else LANE_BG
        self.head.configure(fg_color=bg)
        if self.app.root.focus_get() is not self.name._entry:
            self.name.configure(fg_color=bg, border_color=bg)
        if on:
            self.stripe.place(x=0, y=0, relheight=1)
        else:
            self.stripe.place_forget()
        self.canvas.configure(bg=SELECTED_WAVE if on else PANEL)
        self.refresh_volume_row()
        self.draw()

    def refresh_buttons(self):
        for btn, on, cols in ((self.mute_btn, self.track.mute, MUTE_ON),
                              (self.solo_btn, self.track.solo, SOLO_ON)):
            if on:
                btn.configure(fg_color=cols[0], border_color=cols[1], text_color=cols[2],
                              hover_color=cols[0], border_width=1)
            else:
                btn.configure(fg_color=BTN, border_color=BORDER2, text_color=BTN_TXT,
                              hover_color=BTN_HOVER, border_width=1)
        if self.track.auto_on:
            self.auto_btn.configure(fg_color=GREEN_BG, border_color=GREEN_BORDER, text_color=GREEN_TXT,
                                    hover_color=GREEN_BG)
        else:
            self.auto_btn.configure(fg_color=BTN, border_color=BORDER2, text_color=DIM, hover_color=BTN_HOVER)

    def set_silent(self, silent):
        if silent != self.silent:
            self.silent = silent
            self.draw()

    # --- waveform ---
    def bg(self):
        return SELECTED_WAVE if self.selected else PANEL

    def colors(self):
        bg = self.bg()
        if self.silent:
            return blend(self.color, bg, 0.65), blend(self.dim, bg, 0.55)
        if self.track.auto_on:
            return blend(self.color, bg, 0.55), blend(self.dim, bg, 0.55)
        return self.color, self.dim

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        pk = self.track.peaks
        n = max(1, (w - 16) // self.BAR)
        bright, dim = self.colors()
        self.bars = []
        idx = len(pk) * np.arange(n + 1) // n
        mid = h / 2
        frac = self.app.player.position()
        self.played = int(frac * n)
        self.band = c.create_rectangle(0, 0, 0, 0, width=0, fill=PANEL)
        for i in range(n):
            seg = pk[idx[i]:max(idx[i] + 1, idx[i + 1])]
            v = float(seg.max()) if len(seg) else 0.0
            bh = max(1.5, v * (mid - min(10, h / 6)))
            x0 = 8 + i * self.BAR
            self.bars.append(c.create_rectangle(x0, mid - bh, x0 + self.BAR - 1, mid + bh, width=0,
                                                fill=bright if i < self.played else dim, tags="bar"))
        x = 8 + frac * n * self.BAR
        self.playhead = c.create_line(x, 0, x, h, fill=PLAYHEAD, width=2, tags="playhead")
        self.update_band()
        self.draw_auto()

    # --- automation line ---
    def _dur(self):
        return max(1e-3, self.app.player.source_length() / engine.SR)

    def _xy(self, t, v):
        span = max(1, len(self.bars) * self.BAR)
        h = self.canvas.winfo_height()
        return 8 + span * t / self._dur(), self.PAD + (1 - v) * (h - 2 * self.PAD)

    def _tv(self, x, y):
        span = max(1, len(self.bars) * self.BAR)
        h = self.canvas.winfo_height()
        t = max(0.0, min(self._dur(), (x - 8) / span * self._dur()))
        v = max(0.0, min(1.0, 1 - (y - self.PAD) / max(1, h - 2 * self.PAD)))
        return t, v

    def draw_auto(self, hot=None):
        c = self.canvas
        c.delete("auto")
        if not self.track.auto_on or not self.track.auto_pts or not self.bars:
            return
        pts = [self._xy(t, v) for t, v in self.track.auto_pts]
        x_end = 8 + len(self.bars) * self.BAR
        line = [(8, pts[0][1])] + pts + [(x_end, pts[-1][1])]
        h = c.winfo_height()
        bg = self.bg()
        flat = [k for p in line for k in p]
        wash = c.create_polygon(*flat, x_end, h - self.PAD, 8, h - self.PAD, fill=blend(self.color, bg, 0.88),
                                outline="", tags="auto")
        c.tag_lower(wash, "bar")
        c.tag_lower(self.band)
        c.create_line(*flat, fill=self.color, width=2, tags="auto")
        for i, (x, y) in enumerate(pts):
            c.create_oval(x - 4.5, y - 4.5, x + 4.5, y + 4.5, width=2, outline=self.color,
                          fill=self.color if i == hot else bg, tags="auto")
        c.tag_raise("playhead")

    def _point_at(self, e):
        for i, (t, v) in enumerate(self.track.auto_pts):
            x, y = self._xy(t, v)
            if abs(e.x - x) <= 7 and abs(e.y - y) <= 7:
                return i
        return None

    def _near_line(self, e):
        t, _ = self._tv(e.x, e.y)
        _, y = self._xy(t, self.track.level_at(t))
        return abs(e.y - y) <= 7

    def _show_tip(self, i):
        t, v = self.track.auto_pts[i]
        x, y = self._xy(t, v)
        db = "−∞" if v <= 0 else f"{20 * math.log10(v):+.1f}".replace("-", "−")
        self.app.show_auto_tip(self, x, y, f"{db} dB · {fmt_time(t)}")
        self.draw_auto(hot=i)

    def _hide_tip(self):
        if self._pt_drag is None:
            self.app.hide_auto_tip()
            if self.track.auto_on:
                self.draw_auto()

    def _hover(self, e):
        c = self.canvas
        if self._near_edge(c, e):
            c.configure(cursor="sb_v_double_arrow")
            return
        if self.track.auto_on and self._pt_drag is None:
            i = self._point_at(e)
            if i is not None:
                c.configure(cursor="fleur")
                self._show_tip(i)
                return
            c.configure(cursor="plus" if self._near_line(e) else "hand2")
            self._hide_tip()
            return
        c.configure(cursor="hand2")

    def _press(self, e):
        self.app.select(self)
        if self._near_edge(self.canvas, e):
            self._resizing = True
            self.app.resize_start(self, e)
            return
        if self.track.auto_on:
            i = self._point_at(e)
            if i is None and self._near_line(e):
                t, _ = self._tv(e.x, e.y)
                pts = list(self.track.auto_pts)
                pts.append((t, self.track.level_at(t)))
                pts.sort()
                i = pts.index((t, self.track.level_at(t)))
                self.track.set_automation(True, pts)
                self.app.automation_changed(self)
            if i is not None:
                self._pt_drag = i
                self._show_tip(i)
                return
        self._seek(e)

    def _motion(self, e):
        if self._resizing:
            self.app.resize_move(e)
            return
        if self._pt_drag is not None:
            pts = list(self.track.auto_pts)
            i = self._pt_drag
            t, v = self._tv(e.x, e.y)
            last = len(pts) - 1
            if i == 0:
                t = 0.0                       # the ends stay at the start and the end of the song
            elif i == last:
                t = pts[i][0]
            else:
                t = max(pts[i - 1][0] + 0.01, min(pts[i + 1][0] - 0.01, t))
            pts[i] = (t, v)
            self.track.auto_pts = pts
            self.track.set_automation(True, pts)
            self._show_tip(i)
            return
        self._seek(e)

    def _release(self, e):
        if self._resizing:
            self._resizing = False
            self.app.resize_end()
            return
        if self._pt_drag is not None:
            self._pt_drag = None
            self.app.automation_changed(self)

    def _double(self, e):
        if self._near_edge(self.canvas, e):
            self.app.set_track_height(Lane.H_DEF, save=True)
            return
        if not self.track.auto_on:
            return
        i = self._point_at(e)
        if i is not None and 0 < i < len(self.track.auto_pts) - 1:
            pts = list(self.track.auto_pts)
            del pts[i]
            self._pt_drag = None
            self.track.set_automation(True, pts)
            self.app.hide_auto_tip()
            self.draw_auto()
            self.app.automation_changed(self)

    def update_band(self):
        """Faint band behind the waveform showing the loop area."""
        if not self.bars:
            return
        r = self.app.player.region
        n_src = self.app.player.source_length()
        if not r or not n_src:
            self.canvas.coords(self.band, 0, 0, 0, 0)
            return
        span = len(self.bars) * self.BAR
        on = self.app.player.loop
        bg = SELECTED_WAVE if self.selected else PANEL
        self.canvas.itemconfigure(self.band, fill=blend(BAND_ON if on else BAND_OFF, bg, 0.45))
        self.canvas.coords(self.band, 8 + span * r[0] / n_src, 0, 8 + span * r[1] / n_src,
                           self.canvas.winfo_height())

    def update_playhead(self, frac):
        if not self.bars:
            return
        n = len(self.bars)
        new = int(frac * n)
        if new != self.played:
            bright, dim = self.colors()
            lo, hi = sorted((self.played, new))
            col = bright if new > self.played else dim
            for i in range(lo, min(hi, n)):
                self.canvas.itemconfigure(self.bars[i], fill=col)
            self.played = new
        x = 8 + frac * n * self.BAR
        self.canvas.coords(self.playhead, x, 0, x, self.canvas.winfo_height())

    def _seek(self, e):
        n = max(1, len(self.bars))
        self.app.seek((e.x - 8) / (n * self.BAR))

    def destroy(self):
        self.frame.destroy()


class VolumePopover:
    """Compact lanes: V opens a small volume slider under the button."""
    W = 220

    def __init__(self, app, lane):
        self.app, self.lane, self.root = app, lane, app.root
        on = lane.track.auto_on
        f = self.frame = ctk.CTkFrame(self.root, fg_color=POPOVER, border_color=BORDER_POP, border_width=1,
                                      corner_radius=10, width=self.W, height=44)
        f.grid_propagate(False)
        f.grid_columnconfigure(1, weight=1)
        f.grid_rowconfigure(0, weight=1)
        dimc = (lambda c: blend(c, POPOVER, 0.55)) if on else (lambda c: c)
        ctk.CTkLabel(f, text="Vol", font=font(11), text_color=MUTED, width=24).grid(row=0, column=0, padx=(12, 6))
        self.slider = ctk.CTkSlider(f, from_=0, to=100, number_of_steps=100, height=16, command=self.on_change,
                                    progress_color=dimc(lane.color), button_color=dimc(KNOB),
                                    button_hover_color=dimc(KNOB_HOVER), fg_color=dimc(BORDER2),
                                    state="disabled" if on else "normal")
        self.slider.set(round(lane.track.volume * 100))
        self.slider.grid(row=0, column=1, sticky="ew")
        self.lbl = ctk.CTkLabel(f, text="Auto" if on else f"{round(lane.track.volume * 100)}%", width=38,
                                font=font(11, mono=True), text_color=MUTED, anchor="e")
        self.lbl.grid(row=0, column=2, padx=(6, 12))
        self.place()

    def on_change(self, v):
        self.lane.vol.set(v)
        self.lane.on_volume(v)
        self.lbl.configure(text=f"{int(round(v))}%")

    def place(self):
        r, a = self.root, self.lane.v_btn
        r.update_idletasks()
        x = a.winfo_rootx() - r.winfo_rootx() + a.winfo_width() / 2 - self.W / 2 + 40
        y = a.winfo_rooty() - r.winfo_rooty() + a.winfo_height() + 6
        self.frame.place(x=max(12, min(x, r.winfo_width() - self.W - 12)), y=y)
        self.frame.lift()

    def is_open(self):
        return bool(self.frame.winfo_exists() and self.frame.winfo_ismapped())

    def close(self):
        if self.frame.winfo_exists():
            self.frame.destroy()


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


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class App:
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
        self.yt_job = None
        self.yt_pop = None
        self.selected = None
        self._drag = None
        self._yt_status = None
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

    # ----- layout -----
    def _build_ui(self):
        self.root.configure(fg_color=BG)
        self._build_header()
        main = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        main.grid(row=1, column=0, sticky="nsew", padx=24, pady=(16, 18))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        self._build_dropzone(main)
        self._build_tracks(main)
        self._build_master(main)

    def apply_theme(self, mode):
        """Switch light/dark: the window is rebuilt in the new colours; tracks, settings and
        playback carry on untouched. Remembered for next time."""
        mode = "light" if mode == "light" else "dark"
        settings.put("theme", mode)
        if mode == theme.MODE:
            return
        reopen = self.settings_pop is not None and self.settings_pop.frame.winfo_exists() \
            and self.settings_pop.is_open()
        upd = None
        if self.settings_pop is not None:
            upd = (self.settings_pop.state, self.settings_pop.release, self.settings_pop.stage)
        if self.export_dialog is not None and self.export_dialog.win.winfo_exists():
            self.export_dialog.close()
        sel = self.lanes.index(self.selected) if self.selected in self.lanes else None
        status = self.status.cget("text")
        fader_pos = self.fader.pos
        theme.set_mode(mode)
        self.vol_pop = self.auto_tip = self._resize_hint = None
        for w in list(self.root.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        self.lanes, self.selected = [], None
        self.yt_pop = self.recent_pop = self.settings_pop = self.alert_win = self.export_dialog = None
        self._yt_status = self._shown_playing = self._ruler_len = None
        self._build_ui()
        for i, t in enumerate(self.player.tracks):
            lane = Lane(self, self.lanes_box, t, TRACK_COLORS[i % len(TRACK_COLORS)])
            lane.vol.set(round(t.volume * 100))
            lane.on_volume(round(t.volume * 100))
            self.lanes.append(lane)
        self.speed_slider.set(self.speed)
        self.on_speed(self.speed)
        self.pitch_slider.set(self.semis)
        self.on_pitch(self.semis)
        self.auto_var.set(self.auto)
        self.fine_slider.configure(state="normal")
        self.fine_slider.set(self.current_cents())
        self._style_fine()
        self.fade_slider.set(self.player.loop_fade)
        self.on_fade(self.player.loop_fade)
        self._style_loop()
        self.fader.set_pos(fader_pos)
        self.fader.show_clip(self.player.clip)
        self.status.configure(text=status)
        self.refresh_all()
        self.refresh_lanes()
        self.refresh_region()
        if sel is not None and sel < len(self.lanes):
            self.select(self.lanes[sel])
        self._update_busy()
        self._update_title()
        self._draw_drop()
        if reopen:
            self.open_settings()
            if upd and upd[0] in ("latest", "newer", "ready", "error"):
                self.settings_pop.state, self.settings_pop.release, self.settings_pop.stage = upd
                self.settings_pop.refresh()

    def _build_header(self):
        bar = ctk.CTkFrame(self.root, fg_color=HEADER, corner_radius=0, height=64)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, padx=24, pady=14, sticky="w")
        logo = tk.Canvas(left, width=24, height=24, bg=HEADER, highlightthickness=0)
        for x, h in ((3, 4), (8, 12), (13, 20), (18, 10), (23, 4)):
            logo.create_line(x - 1, 12 - h / 2, x - 1, 12 + h / 2, fill=ACCENT, width=2, capstyle="round")
        logo.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(left, text=APP_NAME, font=font(16, "bold"), text_color=TEXT).pack(side="left")
        self.song_sep = ctk.CTkLabel(left, text="  ·  ", font=font(14), text_color=MUTED)
        self.song_lbl = ctk.CTkLabel(left, text="", font=font(14), text_color=SOFT)
        self.status = ctk.CTkLabel(bar, text="", font=font(12), text_color=AMBER_TXT)
        self.status.grid(row=0, column=1, sticky="e", padx=12)
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, padx=24, pady=14, sticky="e")
        openbox = ctk.CTkFrame(right, fg_color="transparent")
        openbox.pack(side="left", padx=4)
        self.open_btn = ToolButton(openbox, "Open…", self.open_dialog, width=76, corner_radius=8)
        self.open_btn.pack(side="left")
        self.recent_btn = ToolButton(openbox, "", self.open_recent, width=28, image=icon("chevron", TEXT2, 12))
        self.recent_btn.pack(side="left", padx=(2, 0))
        self.save_btn = ToolButton(right, "Save…", lambda: self.save_project(), width=76)
        self.save_btn.pack(side="left", padx=4)
        self.yt_btn = ToolButton(right, "From YouTube…", self.open_youtube, image=icon("youtube", ACCENT_SOFT, 18),
                                 compound="left", width=168)
        self.yt_btn.pack(side="left", padx=4)
        self.export_btn = ToolButton(right, "Export…", self.open_export, primary=True,
                                     image=icon("export", ACCENT_TXT, 15), compound="left")
        self.export_btn.pack(side="left", padx=(4, 0))
        self.cog_btn = ToolButton(right, "", self.open_settings, width=40, image=icon("cog", TEXT2, 18))
        self.cog_btn.pack(side="left", padx=(12, 0))
        self.settings_pop = None
        self._style_cog()
        line = ctk.CTkFrame(self.root, fg_color=BORDER, height=1, corner_radius=0)
        line.grid(row=0, column=0, sticky="sew")

    def _build_dropzone(self, parent):
        self.drop = tk.Canvas(parent, height=64, bg=BG, highlightthickness=0, cursor="hand2")
        self.drop.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.drop.bind("<Configure>", lambda e: self._draw_drop())
        self.drop.bind("<Button-1>", lambda e: self.open_dialog())
        self._drop_hot = False

    def _draw_drop(self):
        c = self.drop
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        hot = self._drop_hot
        c.create_rectangle(1, 1, w - 2, h - 2, outline=ACCENT if hot else CONTROL2, dash=(6, 4),
                           width=2 if hot else 1.5, fill=DROP_HOT if hot else PANEL)
        if self.loading:
            msg = f"Loading {self.loading} file{'s' if self.loading > 1 else ''}…"
        elif hot:
            msg = "Drop to add tracks"
        elif self.dnd:
            msg = "Drop audio files here to add tracks · WAV, FLAC, MP3, M4A, OGG — or click to browse"
        else:
            msg = "Click to add audio files · WAV, FLAC, MP3, M4A, OGG"
        c.create_text(w / 2 + 12, h / 2, text=msg, fill=TEXT2 if hot else BTN_TXT, font=(UI, 11))
        tx = w / 2 - c.tk.call("font", "measure", (UI, 11), msg) / 2 - 8
        c.create_line(tx, h / 2 + 7, tx, h / 2 - 7, fill=ACCENT, width=2, arrow="last", arrowshape=(6, 6, 3))

    def _drop_highlight(self, on):
        self._drop_hot = on
        self._draw_drop()

    def _build_tracks(self, parent):
        box = ctk.CTkFrame(parent, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=12)
        box.grid(row=1, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)
        box.grid_rowconfigure(1, weight=1)
        ruler = ctk.CTkFrame(box, fg_color="transparent", height=30)
        ruler.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 0))
        ruler.grid_columnconfigure(1, weight=1)
        cnt = ctk.CTkFrame(ruler, fg_color="transparent", width=HEAD_W - 16, height=30)
        cnt.grid(row=0, column=0, padx=(14, 2))
        cnt.grid_propagate(False)
        cnt.grid_columnconfigure(0, weight=1)
        cnt.grid_rowconfigure(0, weight=1)
        self.count_lbl = ctk.CTkLabel(cnt, text="NO TRACKS", font=font(11), text_color=MUTED, anchor="w")
        self.count_lbl.grid(row=0, column=0, sticky="w")
        self.compact_btn = ctk.CTkButton(cnt, text="", width=28, height=22, corner_radius=6, border_width=1,
                                         command=self.toggle_compact)
        self.compact_btn.grid(row=0, column=1, padx=(0, 4))
        self._style_compact()
        self.ruler = tk.Canvas(ruler, height=30, bg=PANEL, highlightthickness=0, cursor="xterm")
        self.ruler.grid(row=0, column=1, sticky="ew")
        self.ruler.bind("<Configure>", lambda e: self.draw_ruler())
        self.ruler.bind("<Button-1>", self._ruler_press)
        self.ruler.bind("<B1-Motion>", self._ruler_drag)
        self.ruler.bind("<ButtonRelease-1>", self._ruler_release)
        self.ruler.bind("<Motion>", self._ruler_hover)
        self._rdrag = None
        ctk.CTkFrame(box, fg_color=BORDER, height=1, corner_radius=0).grid(row=0, column=0, sticky="sew")
        self.lanes_box = ctk.CTkScrollableFrame(box, fg_color=PANEL, corner_radius=0,
                                                scrollbar_button_color=BORDER2,
                                                scrollbar_button_hover_color=CONTROL2)
        self.lanes_box.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))
        self.lanes_box.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(self.lanes_box, font=font(14), text_color=MUTED, justify="center",
                                  text="No tracks yet.\nDrop a song, a karaoke file or a set of stems "
                                       "above — or click Open…")

    def _build_master(self, parent):
        box = ctk.CTkFrame(parent, fg_color=PANEL, border_color=BORDER2, border_width=1, corner_radius=12)
        box.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        box.grid_columnconfigure(0, weight=1)
        body = ctk.CTkFrame(box, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=20, pady=16)
        body.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_columnconfigure(0, weight=1)

        # transport
        tr = ctk.CTkFrame(left, fg_color="transparent")
        tr.grid(row=0, column=0, pady=(0, 14))
        self.time_lbl = ctk.CTkLabel(tr, text="0:00 / 0:00", font=font(15, mono=True), text_color=TEXT2,
                                     width=150, anchor="e")
        self.time_lbl.grid(row=0, column=0, padx=(0, 18))
        ctk.CTkButton(tr, text="", image=icon("back", TEXT2, 16), width=44, height=44, corner_radius=22,
                      fg_color=BTN, hover_color=BTN_HOVER, border_color=BORDER2, border_width=1,
                      text_color=TEXT2, command=lambda: self.seek(0)).grid(row=0, column=1, padx=9)
        self.play_btn = ctk.CTkButton(tr, text="", image=icon("play", ACCENT_TXT, 28), width=72, height=72,
                                      corner_radius=36, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                      text_color=ACCENT_TXT, command=self.toggle_play)
        self.play_btn.grid(row=0, column=2, padx=9)
        self.loop_btn = ctk.CTkButton(tr, text="", width=44, height=44, corner_radius=22,
                                      border_width=1, command=self.toggle_loop)
        self.loop_btn.grid(row=0, column=3, padx=9)
        fade = self.fade_box = ctk.CTkFrame(tr, fg_color="transparent", width=170, height=44)
        fade.grid(row=0, column=4, padx=(18, 0))
        fade.grid_propagate(False)
        fade.pack_propagate(False)
        self.fade_inner = ctk.CTkFrame(fade, fg_color="transparent")
        ctk.CTkLabel(self.fade_inner, text="Fade", font=font(12), text_color=MUTED, width=34).pack(side="left")
        self.fade_slider = ctk.CTkSlider(self.fade_inner, from_=0, to=2, number_of_steps=20, width=84, height=16,
                                         command=self.on_fade, progress_color=ACCENT, button_color=TEXT2,
                                         button_hover_color=KNOB_HOVER, fg_color=BORDER2)
        self.fade_slider.set(engine.LOOP_FADE)
        self.fade_slider.pack(side="left", padx=4)
        self.fade_val = ctk.CTkLabel(self.fade_inner, text="1.0 s", font=font(12, mono=True),
                                     text_color=ACCENT_SOFT, width=40, anchor="w")
        self.fade_val.pack(side="left")
        self.ctrl_reset(self.fade_slider, engine.LOOP_FADE, self.on_fade)
        self._style_loop()

        # speed / pitch / fine tune + master fader
        cards = ctk.CTkFrame(left, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew")
        for i in range(3):
            cards.grid_columnconfigure(i, weight=1, uniform="card")

        self.speed_val, self.speed_slider = self._card(
            cards, 0, "Speed", 0.5, 1.5, 20, 1.0, self.on_speed, ("0.5×", "1.0×", "1.5×"))
        self.pitch_val, self.pitch_slider = self._card(
            cards, 1, "Pitch", -6, 6, 12, 0, self.on_pitch, ("−6", "0", "+6"))

        # fine tune card (with Auto 440)
        fc = ctk.CTkFrame(cards, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=10)
        fc.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        self.fine_card = fc
        top = ctk.CTkFrame(fc, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(top, text="Fine-tune", font=font(14, "bold"), text_color=TEXT).pack(side="left")
        self.fine_val = ctk.CTkLabel(top, text="0 ct", font=font(13, "bold", True), anchor="w")
        self.fine_val.pack(side="left", padx=(10, 0))

        ctk.CTkLabel(top, text=" BETA ", font=font(9, "bold"), text_color=AMBER, fg_color=AMBER_BADGE,
                     corner_radius=4, height=18).pack(side="right")
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_chk = ctk.CTkSwitch(top, text="Auto 440", variable=self.auto_var, command=self.on_auto,
                                      font=font(12), text_color=AMBER, switch_width=34, switch_height=18,
                                      fg_color=SWITCH_OFF, progress_color=AMBER, button_color=SWITCH_KNOB,
                                      button_hover_color=SWITCH_KNOB, width=0)
        self.auto_chk.pack(side="right", padx=(0, 6))
        self.fine_slider = ctk.CTkSlider(fc, from_=-50, to=50, number_of_steps=100, height=18,
                                         command=self.on_fine)
        self.fine_slider.set(0)
        self.fine_slider.pack(fill="x", padx=16)
        self.ctrl_reset(self.speed_slider, 1.0, self.on_speed)
        self.ctrl_reset(self.pitch_slider, 0, self.on_pitch)
        self.ctrl_reset(self.fine_slider, 0, self.on_fine)
        self.fine_scale = sc = ctk.CTkFrame(fc, fg_color="transparent")
        ctk.CTkLabel(sc, text="−50 ct", font=font(11, mono=True), text_color=DIM, height=20).pack(side="left")
        ctk.CTkLabel(sc, text="+50 ct", font=font(11, mono=True), text_color=DIM, height=20).pack(side="right")
        ctk.CTkLabel(sc, text="0", font=font(11, mono=True), text_color=DIM, height=20).pack(side="left", expand=True)
        sc.pack(fill="x", padx=16, pady=(4, 0))
        note = ctk.CTkLabel(fc, text="Fine-tuning slightly changes the length of the track.", font=font(11),
                            text_color=DIM, anchor="w", justify="left", wraplength=260)
        note.pack(fill="x", padx=16, pady=(0, 12))
        fc.bind("<Configure>", lambda e: note.configure(wraplength=max(160, e.width - 40)), add="+")
        self._style_fine()

        bottom = ctk.CTkFrame(cards, fg_color="transparent")
        bottom.grid(row=1, column=0, columnspan=3, pady=(12, 0))
        ctk.CTkButton(bottom, text="Reset", height=32, corner_radius=6, font=font(13),
                      fg_color="transparent", hover_color=BTN_HOVER, border_color=BORDER2,
                      border_width=1, text_color=BTN_TXT, command=self.reset_stretch).pack(side="left")
        self.busy_lbl = ctk.CTkLabel(bottom, text="", font=font(12), text_color=ACCENT_SOFT, compound="left")
        self.busy_lbl.pack(side="left", padx=14)

        self.fader = MasterFader(self, body)
        self.fader.card.grid(row=0, column=1, sticky="ns")

    def _card(self, parent, col, title, lo, hi, steps, value, command, marks):
        card = ctk.CTkFrame(parent, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=10)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 8 if col < 2 else 0))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(top, text=title, font=font(14, "bold"), text_color=TEXT).pack(side="left")
        val = ctk.CTkLabel(top, text="", font=font(13, "bold", True), text_color=ACCENT_SOFT)
        val.pack(side="right")
        sl = ctk.CTkSlider(card, from_=lo, to=hi, number_of_steps=steps, height=18, command=command,
                           progress_color=ACCENT, button_color=KNOB, button_hover_color=KNOB_HOVER,
                           fg_color=BORDER2)
        sl.set(value)
        sl.pack(fill="x", padx=16)
        self._marks(card, marks).pack(fill="x", padx=16, pady=(4, 12))
        return val, sl

    @staticmethod
    def _marks(parent, marks):
        sc = ctk.CTkFrame(parent, fg_color="transparent")
        lo, mid, hi = (ctk.CTkLabel(sc, text=m, font=font(11, mono=True), text_color=DIM, height=20)
                       for m in marks)
        lo.pack(side="left")
        hi.pack(side="right")
        mid.pack(side="left", expand=True)
        return sc

    @staticmethod
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

    # ----- styling helpers -----
    def _style_loop(self):
        on = self.player.loop
        if on:
            self.fade_inner.place(relx=0, rely=0.5, anchor="w")
        else:
            self.fade_inner.place_forget()
        self.loop_btn.configure(fg_color=ACCENT_TINT if on else BTN, border_color=ACCENT if on else BORDER2,
                                image=icon("loop", ACCENT_SOFT if on else TEXT2, 18),
                                hover_color=ACCENT_TINT_HOVER if on else BTN_HOVER)

    def _style_fine(self):
        auto = self.auto
        self.fine_card.configure(fg_color=GREEN_BG if auto else CARD,
                                 border_color=GREEN_BORDER if auto else BORDER)
        col = GREEN if auto else ACCENT
        self.fine_slider.configure(progress_color=col, button_color=col if auto else TEXT2,
                                   button_hover_color=col if auto else KNOB_HOVER,
                                   fg_color=GREEN_TRACK if auto else BORDER2,
                                   state="disabled" if auto else "normal")
        text = "…" if (auto and self.analysing) else cents_text(self.current_cents())
        self.fine_val.configure(text=text, text_color=GREEN if auto else ACCENT_SOFT)

    # ----- files -----
    def open_dialog(self):
        exts = " ".join("*" + e for e in sorted(engine.AUDIO_EXTS))
        paths = filedialog.askopenfilenames(
            parent=self.root, title="Open audio files or a project", initialdir=self.last_dir,
            filetypes=[("Audio files and projects", exts + " *" + project.EXT), ("Audio files", exts),
                       ("NiSH Player projects", "*" + project.EXT), ("All files", "*.*")])
        if paths:
            self.open_paths(paths)

    def open_paths(self, paths):
        """Audio files are added; a project file replaces the workspace."""
        projects = [p for p in paths if str(p).lower().endswith(project.EXT)]
        if projects:
            self.open_project(projects[0])
        audio = [p for p in paths if not str(p).lower().endswith(project.EXT)]
        if audio:
            self.add_files(audio)

    def _on_drop(self, event):
        self._drop_highlight(False)
        self.open_paths(self.root.tk.splitlist(event.data))
        return event.action

    def add_files(self, paths, names=None, prefer_names=False):
        """names: optional {path: track name} for files that have no saved name yet
        (prefer_names: these names win, as when opening a project)."""
        files = []
        for p in paths:
            p = Path(p)
            if p.is_dir():
                files += sorted(q for q in p.iterdir() if q.suffix.lower() in engine.AUDIO_EXTS)
            elif p.suffix.lower() in engine.AUDIO_EXTS:
                files.append(p)
        have = {str(Path(l.track.path).resolve()) for l in self.lanes}
        files = [f for f in dict.fromkeys(files) if str(f.resolve()) not in have]
        if not files:
            if paths:
                self.flash("Those files are already loaded or aren't audio files.")
            return
        self.last_dir = str(files[0].parent)
        self.loading += len(files)
        self._draw_drop()
        labels = engine.load_labels()
        names = {str(Path(k).resolve()): v for k, v in (names or {}).items()}

        def work():  # one after another, so the lanes keep the order of the files
            for f in files:
                key = str(f.resolve())
                try:
                    audio = engine.decode(f)
                    name = (names.get(key) or labels.get(key)) if prefer_names else (labels.get(key) or names.get(key))
                    self.events.put(("loaded", f, audio, name))
                except Exception as e:
                    self.events.put(("load_error", f, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _add_track(self, path, audio, label):
        track = engine.Track(path, audio, label)
        lane = Lane(self, self.lanes_box, track, TRACK_COLORS[len(self.lanes) % len(TRACK_COLORS)])
        self.lanes.append(lane)
        self.player.add(track)
        if self.selected is None:
            self.select(lane)
        t = (self._restore or {}).get("tracks", {}).get(str(Path(path).resolve()))
        if t:
            lane.vol.set(round(t.get("volume", 1.0) * 100))
            lane.on_volume(round(t.get("volume", 1.0) * 100))
            track.mute, track.solo = bool(t.get("mute")), bool(t.get("solo"))
            a = t.get("automation")
            if isinstance(a, dict) and a.get("points"):
                try:
                    lane.set_automation(bool(a.get("on")), [(float(x), float(y)) for x, y in a["points"]])
                except (TypeError, ValueError):
                    pass
            self.refresh_lanes()
        self.refresh_all()
        if self.auto and not (self._restore and self.auto_result):
            self.start_analysis()
        self._update_busy()

    # ----- track height (one for all lanes), compact mode -----
    def set_track_height(self, h, save=False):
        h = int(max(Lane.H_MIN, min(Lane.H_MAX, round(h))))
        if h != self.track_h:
            if self.track_h >= Lane.H_COMPACT and h < Lane.H_COMPACT:
                self.close_vol_pop()
            self.track_h = h
            for lane in self.lanes:
                lane.set_height(h)
            self._style_compact()
        if save:
            settings.put("track_height", self.track_h)
            if self.track_h >= Lane.H_COMPACT:
                self.prev_h = self.track_h
                settings.put("track_height_prev", self.prev_h)

    def toggle_compact(self):
        """Smallest height, and back to the previous height."""
        if self.track_h < Lane.H_COMPACT:
            prev = self.prev_h if isinstance(self.prev_h, int) and self.prev_h >= Lane.H_COMPACT else Lane.H_DEF
            self.set_track_height(prev, save=True)
        else:
            self.prev_h = self.track_h
            settings.put("track_height_prev", self.prev_h)
            self.set_track_height(Lane.H_MIN, save=True)

    def _style_compact(self):
        if not hasattr(self, "compact_btn"):
            return
        on = self.track_h < Lane.H_COMPACT
        self.compact_btn.configure(image=icon("compact", ACCENT_TXT if on else SOFT, 14),
                                   fg_color=ACCENT_TINT if on else BTN, border_color=ACCENT if on else BORDER2,
                                   hover_color=ACCENT_TINT_HOVER if on else BTN_HOVER)

    def resize_start(self, lane, e):
        self._resize = (e.y_root, self.track_h, lane)
        self.hide_auto_tip()
        lane.line.configure(fg_color=ACCENT, height=2)
        self._show_resize_hint(lane)

    def resize_move(self, e):
        if not self._resize:
            return
        y0, h0, lane = self._resize
        self.set_track_height(h0 + (e.y_root - y0))
        self._show_resize_hint(lane)

    def resize_end(self):
        if not self._resize:
            return
        lane = self._resize[2]
        self._resize = None
        if lane.frame.winfo_exists():
            lane.line.configure(fg_color=BORDER, height=1)
        if self._resize_hint is not None and self._resize_hint.winfo_exists():
            self._resize_hint.place_forget()
        self.set_track_height(self.track_h, save=True)

    def _show_resize_hint(self, lane):
        r = self.root
        if self._resize_hint is None or not self._resize_hint.winfo_exists():
            self._resize_hint = ctk.CTkLabel(r, text="", font=font(11, "bold", True), fg_color=ACCENT,
                                             text_color=ACCENT_TXT, corner_radius=10, height=20)
        self._resize_hint.configure(text=f"  ↕ {self.track_h} px · all tracks  ")
        r.update_idletasks()
        x = lane.line.winfo_rootx() - r.winfo_rootx() + HEAD_W / 2
        y = lane.line.winfo_rooty() - r.winfo_rooty() - 9
        self._resize_hint.place(x=x, y=y, anchor="center")
        self._resize_hint.lift()

    def toggle_vol_pop(self, lane):
        self.select(lane)
        same = self.vol_pop is not None and self.vol_pop.lane is lane and self.vol_pop.is_open()
        self.close_vol_pop()
        if not same:
            self.vol_pop = VolumePopover(self, lane)
            lane.refresh_v()

    def close_vol_pop(self):
        pop, self.vol_pop = self.vol_pop, None
        if pop is not None:
            pop.close()
            if pop.lane in self.lanes:
                pop.lane.refresh_v()

    def _click_anywhere(self, e):
        """Close the volume popover when clicking outside it."""
        pop = self.vol_pop
        if pop is None or not pop.is_open():
            return
        w = e.widget
        try:
            path = str(w)
        except Exception:
            return
        if path.startswith(str(pop.frame)) or path.startswith(str(pop.lane.v_btn)):
            return
        self.close_vol_pop()

    def volume_changed(self, lane):
        pop = self.vol_pop
        if pop is not None and pop.lane is lane and pop.is_open():
            pop.lbl.configure(text=f"{round(lane.track.volume * 100)}%")

    def automation_changed(self, lane):
        """Automation edited or switched: the popover and the window title (unsaved •) follow."""
        pop = self.vol_pop
        if pop is not None and pop.lane is lane:
            self.close_vol_pop()
        self._update_title()

    def show_auto_tip(self, lane, x, y, text):
        """Value tip over an automation point: popover background, border in the track colour."""
        r = self.root
        if self.auto_tip is None or not self.auto_tip.winfo_exists():
            self.auto_tip = tk.Label(r, text="", font=(MONO, 9), bg=POPOVER, fg=TEXT, padx=7, pady=2,
                                     highlightthickness=1, bd=0)
        tip = self.auto_tip
        tip.configure(text=text, highlightbackground=lane.color, highlightcolor=lane.color)
        c = lane.canvas
        tip.place(x=c.winfo_rootx() - r.winfo_rootx() + x, y=c.winfo_rooty() - r.winfo_rooty() + y - 10,
                  anchor="s")
        tip.lift()

    def hide_auto_tip(self):
        if self.auto_tip is not None and self.auto_tip.winfo_exists():
            self.auto_tip.place_forget()

    # ----- selection, exclusive solo, reordering -----
    def select(self, lane):
        if self.selected is lane:
            return
        if self.selected is not None and self.selected in self.lanes:
            self.selected.set_selected(False)
        self.selected = lane
        if lane is not None:
            lane.set_selected(True)

    def solo_only(self, lane):
        """Solo just this track (Ctrl+click on S). Again on the only solo turns it off."""
        self.select(lane)
        only = lane.track.solo and not any(l.track.solo for l in self.lanes if l is not lane)
        for l in self.lanes:
            l.track.solo = (l is lane) and not only
        self.refresh_lanes()

    def drag_start(self, lane, e):
        self.select(lane)
        self._drag = lane
        lane.grip.configure(image=icon("grip", ACCENT, 14))

    def drag_move(self, lane, e):
        if self._drag is not lane:
            return
        y = e.y_root
        i = self.lanes.index(lane)
        target = i
        for j, other in enumerate(self.lanes):
            top = other.frame.winfo_rooty()
            mid = top + other.frame.winfo_height() / 2
            if j < i and y < mid:
                target = j
                break
            if j > i and y > mid:
                target = j
        if target != i:
            self.move_lane(lane, target)

    def drag_end(self, lane, e):
        self._drag = None
        lane.grip.configure(image=icon("grip", GRIP, 14))

    def move_lane(self, lane, index):
        self.lanes.remove(lane)
        self.lanes.insert(index, lane)
        with self.player.lock:
            self.player.tracks = [l.track for l in self.lanes]
        for i, l in enumerate(self.lanes):
            l.frame.grid(row=i, column=0, sticky="ew")

    def _selected_key(self, action):
        if self._typing() or self.selected is None or self.selected not in self.lanes:
            return None
        action(self.selected)
        return "break"

    def remove_lane(self, lane):
        if self.vol_pop is not None and self.vol_pop.lane is lane:
            self.close_vol_pop()
        self.hide_auto_tip()
        if self.selected is lane:
            self.selected = None
        self.player.remove(lane.track)
        lane.destroy()
        self.lanes.remove(lane)
        self.refresh_all()
        if self.auto:
            self.start_analysis()

    def clear_all(self):
        self.close_vol_pop()
        self.hide_auto_tip()
        self.player.clear()
        self.selected = None
        for lane in self.lanes:
            lane.destroy()
        self.lanes = []
        self.auto_result = None
        self.refresh_all()
        self._style_fine()

    def refresh_all(self):
        for i, lane in enumerate(self.lanes):
            lane.frame.grid(row=i, column=0, sticky="ew")
        if self.lanes:
            self.empty.grid_forget()
            n = len(self.lanes)
            self.count_lbl.configure(text=f"{n} TRACK{'S' if n > 1 else ''}")
            self.song_lbl.configure(text=engine.song_name([l.track.path for l in self.lanes]))
            self.song_sep.pack(side="left")
            self.song_lbl.pack(side="left")
        else:
            self.empty.grid(row=0, column=0, pady=60)
            self.count_lbl.configure(text="NO TRACKS")
            self.song_sep.pack_forget()
            self.song_lbl.pack_forget()
        self.refresh_lanes()
        self.draw_ruler()

    def refresh_lanes(self):
        gains = self.player.gains()
        for lane, g in zip(self.lanes, gains):
            lane.refresh_buttons()
            lane.set_silent(g <= 0)

    def _ruler_span(self):
        if not self.lanes:
            return 1
        return max(1, len(self.lanes[0].bars) * Lane.BAR)

    def _x_to_src(self, x):
        n = self.player.source_length()
        return max(0.0, min(1.0, (x - 8) / self._ruler_span())) * n

    def _src_to_x(self, p):
        n = self.player.source_length() or 1
        return 8 + self._ruler_span() * p / n

    def draw_ruler(self):
        c = self.ruler
        c.delete("all")
        n = self.player.length()
        if not n or not self.lanes:
            return
        span = self._ruler_span()
        dur = n / engine.SR
        r = self.player.region
        if r:   # the loop area, behind the time marks
            on = self.player.loop
            x0, x1 = self._src_to_x(r[0]), self._src_to_x(r[1])
            c.create_rectangle(x0, 2, x1, 29, width=0, fill=ACCENT_BAND if on else RANGE_IDLE)
            edge = ACCENT if on else CONTROL
            c.create_line(x0, 2, x0, 29, fill=edge, width=2)
            c.create_line(x1, 2, x1, 29, fill=edge, width=2)
            if on:   # the fades, as slopes at both ends
                fw = (x1 - x0) * engine.loop_fade_len(r[0], r[1], self.player.loop_fade) / max(1, r[1] - r[0])
                if fw >= 1:
                    c.create_line(x0, 29, x0 + fw, 3, fill=ACCENT_SOFT, width=1)
                    c.create_line(x1 - fw, 3, x1, 29, fill=ACCENT_SOFT, width=1)
            sp = self.player.speed
            label = f"{fmt_time(r[0] / engine.SR / sp)} – {fmt_time(r[1] / engine.SR / sp)}"
            if x1 - x0 > 110:
                c.create_text((x0 + x1) / 2, 15, text=label, fill=ACCENT_SOFT if on else MUTED,
                              font=(MONO, 9))
            cx = x1 - 9 if x1 - x0 > 40 else x1 + 10
            c.create_text(cx, 15, text="×", fill=TEXT2, font=(UI, 12), tags=("clear",))
        step = next((s for s in (5, 10, 15, 20, 30, 60, 120, 300) if dur / s <= 9), 600)
        t = 0
        while t <= dur:
            x = 8 + span * t / dur
            c.create_line(x, 23, x, 29, fill=BORDER2)
            if not r:
                c.create_text(x + 3, 14, text=fmt_time(t), anchor="w", fill=MUTED, font=(MONO, 9))
            else:
                c.create_text(x + 3, 9, text=fmt_time(t), anchor="w", fill=DIM, font=(MONO, 8))
            t += step
        self._ruler_len = (n, r, self.player.loop, self.player.loop_fade)

    def refresh_region(self):
        self.draw_ruler()
        for lane in self.lanes:
            lane.update_band()

    def _ruler_hit(self, x):
        r = self.player.region
        if not r:
            return None
        x0, x1 = self._src_to_x(r[0]), self._src_to_x(r[1])
        if "clear" in self.ruler.gettags(self.ruler.find_closest(x, 15)[0]) and \
                abs(x - (x1 - 9 if x1 - x0 > 40 else x1 + 10)) < 8:
            return "clear"
        if abs(x - x0) < 7:
            return "a"
        if abs(x - x1) < 7:
            return "b"
        if x0 < x < x1:
            return "move"
        return None

    def _ruler_hover(self, e):
        hit = self._ruler_hit(e.x)
        self.ruler.configure(cursor={"a": "sb_h_double_arrow", "b": "sb_h_double_arrow", "move": "fleur",
                                     "clear": "hand2"}.get(hit, "xterm"))

    def _ruler_press(self, e):
        if not self.lanes:
            return
        self._rdrag = {"x": e.x, "hit": self._ruler_hit(e.x), "region": self.player.region, "moved": False}

    def _ruler_drag(self, e):
        d = self._rdrag
        if not d:
            return
        if not d["moved"] and abs(e.x - d["x"]) < 4:
            return
        d["moved"] = True
        hit, r = d["hit"], d["region"]
        if hit == "a":
            self.player.set_region(self._x_to_src(e.x), r[1])
        elif hit == "b":
            self.player.set_region(r[0], self._x_to_src(e.x))
        elif hit == "move":
            delta = self._x_to_src(e.x) - self._x_to_src(d["x"])
            n = self.player.source_length()
            delta = max(-r[0], min(n - r[1], delta))
            self.player.set_region(r[0] + delta, r[1] + delta)
        else:
            self.player.set_region(self._x_to_src(d["x"]), self._x_to_src(e.x))
        self.refresh_region()

    def _ruler_release(self, e):
        d, self._rdrag = self._rdrag, None
        if not d:
            return
        if not d["moved"]:
            if d["hit"] == "clear":
                self.player.set_region(None, None)
                self.refresh_region()
            else:
                self.seek(self._x_to_src(e.x) / max(1, self.player.source_length()))

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

    # ----- loop -----
    def _tick(self):
        try:
            self._handle_events()
            self._yt_button_tick()
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
            elif kind == "yt_info" and ev[1] is self.yt_pop:
                if isinstance(ev[3], dict) and ev[3].get("error") and ev[3].get("url"):
                    self.note_yt_failure()      # YouTube couldn't read the link
                self.yt_pop.got_info(ev[2], ev[3])
            elif kind == "yt_stage" and ev[1] is self.yt_job:
                ev[1].progress[ev[2]] = ev[3]
                self._yt_refresh()
            elif kind == "open_paths":          # NiSH Player was started again (e.g. a .nish double-click)
                self.bring_to_front()
                if ev[1]:
                    self.open_paths(ev[1])
            elif kind == "settings_refresh":
                if self.settings_pop is not None and self.settings_pop.frame.winfo_exists():
                    self.settings_pop.refresh()
            elif kind == "yt_done" and ev[1] is self.yt_job:
                self._yt_finished(ev[1], ev[2], ev[3])

    # ----- Add from YouTube -----
    def open_youtube(self):
        import youtube_ui
        if self.yt_pop is None or not self.yt_pop.frame.winfo_exists():
            self.yt_pop = youtube_ui.YouTubePopover(self, self.yt_btn)
        elif self.yt_pop.is_open():
            self.yt_pop.close()
            return
        else:
            self.yt_pop.show("work" if self.yt_job else "setup")
            self.yt_pop.place()
        self.yt_pop.url.focus_set()
        self.root.bind("<Escape>", lambda e: self.yt_pop.close() if self.yt_pop and self.yt_pop.is_open() else None)

    def _yt_refresh(self):
        if self.yt_pop and self.yt_pop.is_open() and self.yt_pop.work.winfo_ismapped():
            self.yt_pop.refresh_work()

    def _yt_finished(self, job, result, error):
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
            self._yt_done_until = self.root.winfo_toplevel().tk.call("clock", "milliseconds") + 5000
        self._yt_refresh()

    def _yt_button_tick(self):
        """While a YouTube job runs, the header button becomes a spinner with the current step."""
        job = self.yt_job
        now = int(self.root.tk.call("clock", "milliseconds"))
        if job and job.running:
            frame = (now // 90) % 12
            state = ("spin", frame, job.short_status())
        elif job and job.result and now < getattr(self, "_yt_done_until", 0):
            state = ("done",)
        else:
            state = ("idle",)
        if state == self._yt_status:
            return
        self._yt_status = state
        if state[0] == "spin":
            self.yt_btn.configure(image=icon(f"spin{state[1]}", ACCENT_SOFT, 18), text=state[2],
                                  border_color=ACCENT, text_color=ACCENT_SOFT)
        elif state[0] == "done":
            self.yt_btn.configure(image=icon("check", GREEN, 16), text="Done", border_color=GREEN_BORDER,
                                  text_color=GREEN_TXT)
        else:
            self.yt_btn.configure(image=icon("youtube", ACCENT_SOFT, 18), text="From YouTube…",
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

    # ----- projects -----
    def project_state(self):
        r = self.player.region
        return {
            "tracks": [{"file": str(l.track.path), "name": l.track.label, "volume": round(l.track.volume, 3),
                        "mute": l.track.mute, "solo": l.track.solo,
                        **({"automation": {"on": l.track.auto_on,
                                           "points": [[round(t, 3), round(v, 4)] for t, v in l.track.auto_pts]}}
                           if l.track.auto_pts else {})} for l in self.lanes],
            "speed": self.speed, "pitch": self.semis, "fine": self.manual_cents,
            "auto440": self.auto, "auto440_result": list(self.auto_result) if self.auto_result else None,
            "loop": {"on": self.player.loop, "start": r and round(r[0] / engine.SR, 3),
                     "end": r and round(r[1] / engine.SR, 3), "fade": self.player.loop_fade},
            "master": round(self.fader.pos, 4),
        }

    def is_dirty(self):
        return bool(self.project_path) and project.signature(self.project_state()) != self._saved_sig

    def ask_save_changes(self):
        """True = save, False = don't save, None = cancel."""
        return messagebox.askyesnocancel(APP_NAME, f"Save changes to {Path(self.project_path).stem}?",
                                         parent=self.root)

    def confirm_discard(self):
        """Before closing or replacing the workspace. False = the user cancelled."""
        if not self.is_dirty():
            return True
        ans = self.ask_save_changes()
        if ans is None:
            return False
        if ans:
            return self.save_project()
        return True

    def save_project(self, save_as=False):
        if not self.lanes:
            self.flash("Add some audio first.")
            return False
        path = self.project_path
        if save_as or not path:
            first = Path(self.lanes[0].track.path)
            path = filedialog.asksaveasfilename(
                parent=self.root, title="Save project", defaultextension=project.EXT,
                initialdir=str(Path(path).parent if path else first.parent),
                initialfile=engine.safe_filename(engine.song_name([l.track.path for l in self.lanes])) + project.EXT,
                filetypes=[("NiSH Player project", "*" + project.EXT)])
            if not path:
                return False
        try:
            path = project.save(path, self.project_state())
        except Exception as e:
            traceback.print_exc()
            self.show_alert("Save project", f"The project couldn't be saved:\n{e}")
            return False
        self._set_project(path)
        self.flash(f"Saved {path.name}")
        return True

    def _set_project(self, path, sig=None):
        self.project_path = str(path) if path else None
        self._saved_sig = sig or project.signature(self.project_state())
        self._update_title()

    def main_folder(self):
        """The song's main folder, if there is one: the open project's folder, or for tracks in
        '<Song>/<Song> stems/' (a YouTube import) the '<Song>' folder. Exports go there automatically."""
        if self.project_path:
            return str(Path(self.project_path).parent)
        dirs = {Path(l.track.path).resolve().parent for l in self.lanes if getattr(l.track, "path", None)}
        if len(dirs) == 1:
            d = dirs.pop()
            if d.name.lower().endswith(" stems") and d.parent.name and d.name.lower().startswith(d.parent.name.lower()):
                return str(d.parent)
        return None

    def _update_title(self):
        if self.project_path:
            dot = " •" if self.is_dirty() else ""
            self.root.title(f"{Path(self.project_path).stem}{dot} – {APP_NAME}")
        else:
            self.root.title(APP_NAME)

    def open_project(self, path):
        if not self.confirm_discard():
            return
        try:
            state, missing = project.load(path)
        except Exception as e:
            traceback.print_exc()
            self.show_alert("Open project", f"{Path(path).name} couldn't be opened.\n{e}")
            return
        self.clear_all()
        self.project_path = None
        # settings first, tracks load in the background and pick up their own settings
        self.speed_slider.set(state.get("speed", 1.0))
        self.on_speed(state.get("speed", 1.0))
        self.pitch_slider.set(state.get("pitch", 0))
        self.on_pitch(state.get("pitch", 0))
        self.manual_cents = round(float(state.get("fine", 0)))
        res = state.get("auto440_result")
        self.auto_result = tuple(res) if res else None
        self.auto = bool(state.get("auto440"))
        self.auto_var.set(self.auto)
        self.fine_slider.configure(state="normal")
        self.fine_slider.set(self.current_cents())
        self._style_fine()
        if state.get("master") is not None:
            self.fader.set_pos(state["master"])
        loop = state.get("loop") or {}
        fade = float(loop.get("fade", engine.LOOP_FADE))
        self.fade_slider.set(fade)
        self.on_fade(fade)
        self.player.loop = bool(loop.get("on"))
        self._style_loop()
        self._live(0)
        tracks = state.get("tracks", [])
        self._restore = {"tracks": {str(Path(t["file"]).resolve()): t for t in tracks},
                         "loop": loop, "path": str(path)}
        if missing:
            self.show_alert("Open project", "These tracks couldn't be found and were left out:\n"
                            + "\n".join("• " + m for m in missing[:12]))
        if tracks:
            self.add_files([t["file"] for t in tracks], names={t["file"]: t.get("name") for t in tracks},
                           prefer_names=True)
        else:
            self._finish_restore()

    def _finish_restore(self):
        """All tracks of an opened project are in: the loop area, then 'nothing changed yet'."""
        r = self._restore
        if not r:
            return
        self._restore = None
        loop = r.get("loop") or {}
        if loop.get("start") is not None and loop.get("end") is not None:
            self.player.set_region(loop["start"] * engine.SR, loop["end"] * engine.SR)
            self.refresh_region()
        self.refresh_lanes()
        self._set_project(r["path"])

    def open_recent(self):
        import project_ui
        if self.recent_pop is not None and self.recent_pop.frame.winfo_exists() and self.recent_pop.is_open():
            self.recent_pop.close()
            return
        if self.recent_pop is not None and self.recent_pop.frame.winfo_exists():
            self.recent_pop.frame.destroy()
        self.recent_pop = project_ui.RecentMenu(self, self.open_btn)

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
# Export dialog
# ---------------------------------------------------------------------------

class ExportDialog:
    def __init__(self, app):
        self.app = app
        self.busy = False
        self.written = []
        win = self.win = ctk.CTkToplevel(app.root)
        win.title("Export")
        win.configure(fg_color=HEADER)
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
        for value, title, sub in (("mix", "Mix as you hear it", "One file. Mute, solo and volume are applied."),
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
        if self.region:
            sp = app.player.speed
            span = f"{fmt_time(self.region[0] / engine.SR / sp)} – {fmt_time(self.region[1] / engine.SR / sp)}"
            note = ctk.CTkFrame(body, fg_color=ACCENT_TINT, border_color=ACCENT_LINE, border_width=1,
                                corner_radius=8)
            note.pack(fill="x", pady=(10, 0))
            f = app.player.loop_fade
            fades = "with no fades" if f <= 0 else f"with {f:g}-second fades in and out"
            ctk.CTkLabel(note, text=f"  Loop is on – only the marked area ({span}) will be exported, "
                                    f"{fades}.", font=font(12), text_color=ACCENT_SOFT,
                         wraplength=460, justify="left", image=icon("loop", ACCENT_SOFT, 15),
                         compound="left").pack(anchor="w", padx=12, pady=8)

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
