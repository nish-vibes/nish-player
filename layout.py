"""Builds the main window's widgets: header, tracks box, playback deck, theme."""
import tkinter as tk

import customtkinter as ctk

import engine
from engine import APP_NAME
import settings
import theme
from theme import *  # noqa: F401,F403
from lane import Lane
from widgets import ForkSwitch, MasterFader, ctrl_reset  # noqa: F401


class LayoutMixin:
    """Main window layout (part of App)."""

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
        self.open_btn = ToolButton(openbox, "Open project", self.open_dialog, width=76, corner_radius=8)
        self.open_btn.pack(side="left")
        self.recent_btn = ToolButton(openbox, "", self.open_recent, width=28, image=icon("chevron", TEXT2, 12))
        self.recent_btn.pack(side="left", padx=(2, 0))
        self.save_btn = ToolButton(right, "Save project", lambda: self.save_project(), width=76)
        self.save_btn.pack(side="left", padx=4)
        self.yt_btn = ToolButton(right, "Split", self.open_youtube, image=icon("split", ACCENT_SOFT, 18),
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
        box = ctk.CTkFrame(parent, fg_color=WAVE, border_color=BORDER, border_width=1, corner_radius=12)
        box.grid(row=1, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)
        box.grid_rowconfigure(1, weight=1)
        ruler = ctk.CTkFrame(box, fg_color=LANE_BG, height=30, corner_radius=0)
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
        self.ruler = tk.Canvas(ruler, height=30, bg=LANE_BG, highlightthickness=0, cursor="xterm")
        self.ruler.grid(row=0, column=1, sticky="ew")
        self.ruler.bind("<Configure>", lambda e: self.draw_ruler())
        self.ruler.bind("<Button-1>", self._ruler_press)
        self.ruler.bind("<B1-Motion>", self._ruler_drag)
        self.ruler.bind("<ButtonRelease-1>", self._ruler_release)
        self.ruler.bind("<Motion>", self._ruler_hover)
        self._rdrag = None
        ctk.CTkFrame(box, fg_color=BORDER, height=1, corner_radius=0).grid(row=0, column=0, sticky="sew")
        self.lanes_box = ctk.CTkScrollableFrame(box, fg_color=WAVE, corner_radius=0,
                                                scrollbar_button_color=BORDER2,
                                                scrollbar_button_hover_color=CONTROL2)
        self.lanes_box.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))
        self.lanes_box.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(self.lanes_box, font=font(14), text_color=MUTED, justify="center",
                                  text="No tracks yet.\nDrop a song, a karaoke file or a set of stems "
                                       "above — or click Open…")

    def _build_master(self, parent):
        box = ctk.CTkFrame(parent, fg_color=DECK, border_color=BORDER2, border_width=1, corner_radius=12)
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
                                         command=self.on_fade, progress_color=ACCENT, button_color=ACCENT,
                                         button_hover_color=ACCENT_HOVER, fg_color=ACCENT_TRACK)
        self.fade_slider.set(engine.LOOP_FADE)
        self.fade_slider.pack(side="left", padx=4)
        self.fade_val = ctk.CTkLabel(self.fade_inner, text="1.0 s", font=font(12, mono=True),
                                     text_color=ACCENT_SOFT, width=40, anchor="w")
        self.fade_val.pack(side="left")
        ctrl_reset(self.fade_slider, engine.LOOP_FADE, self.on_fade)
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

        ctk.CTkLabel(top, text=" BETA ", font=font(9, "bold"), text_color=WARN, fg_color=AMBER_BADGE,
                     corner_radius=4, height=18).pack(side="right")
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_chk = ForkSwitch(top, "Auto 440", self.auto_var, self.on_auto)
        self.auto_chk.pack(side="right", padx=(0, 6))
        self.fine_slider = ctk.CTkSlider(fc, from_=-50, to=50, number_of_steps=100, height=18,
                                         command=self.on_fine)
        self.fine_slider.set(0)
        self.fine_slider.pack(fill="x", padx=16)
        ctrl_reset(self.speed_slider, 1.0, self.on_speed)
        ctrl_reset(self.pitch_slider, 0, self.on_pitch)
        ctrl_reset(self.fine_slider, 0, self.on_fine)
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
                           progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                           fg_color=ACCENT_TRACK)
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
        col = WARN if auto else ACCENT
        self.fine_slider.configure(progress_color=col, button_color=col, button_hover_color=col,
                                   fg_color=AMBER_BORDER if auto else ACCENT_TRACK,
                                   state="disabled" if auto else "normal")
        self.auto_chk.set_bg(GREEN_BG if auto else CARD)
        text = "…" if (auto and self.analysing) else cents_text(self.current_cents())
        self.fine_val.configure(text=text, text_color=GREEN if auto else ACCENT_SOFT)
