"""One track lane (header with name, M/S and volume, plus the waveform) and the small volume popover
used in compact mode."""
import math
import tkinter as tk

import customtkinter as ctk
import numpy as np

import engine
from theme import *  # noqa: F401,F403
from widgets import ForkSwitch, MasterFader, ctrl_reset  # noqa: F401


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
        self.frame = ctk.CTkFrame(parent, fg_color=WAVE, corner_radius=0, border_width=0)
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
        self.remove_btn = ctk.CTkButton(head, text="", image=icon("close", DIM, 11), width=24, height=28,
                                        corner_radius=6,
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
                                 button_color=self.color, button_hover_color=self.color, fg_color=self.dim)
        self.vol.set(100)
        ctrl_reset(self.vol, 100, self.on_volume)
        self.vol.grid(row=0, column=2, sticky="ew", padx=(0, 6))

        self.canvas = tk.Canvas(self.frame, height=h, bg=WAVE, highlightthickness=0, cursor="hand2")
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
                           button_color=dimc(self.color) if on else self.color,
                           button_hover_color=dimc(self.color) if on else self.color,
                           fg_color=dimc(self.dim) if on else self.dim)
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
        self.canvas.configure(bg=SELECTED_WAVE if on else WAVE)
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
        return SELECTED_WAVE if self.selected else WAVE

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
        self.band = c.create_rectangle(0, 0, 0, 0, width=0, fill=WAVE)
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
        bg = SELECTED_WAVE if self.selected else WAVE
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
                                    progress_color=dimc(lane.color), button_color=dimc(lane.color),
                                    button_hover_color=dimc(lane.color), fg_color=dimc(lane.dim),
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
