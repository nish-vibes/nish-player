"""The Lux main window (the JAMM Lux mockup on the design canvas, "JAMM Lux · Main window"):
a quiet header, the song in large type with its facts on a warm stage-light glow, the tracks as
rounded cards with the speed & pitch panel beside them, and the transport in one pill at the bottom.

Only used in the Lux theme; Dark and Light keep layout.py's window. It builds the same widgets
under the same names (speed_slider, play_btn, lanes_box, fader, ...), so everything else works as is.
"""
import tkinter as tk

import customtkinter as ctk

import engine
import theme
from theme import *  # noqa: F401,F403
from widgets import ForkSwitch, MasterFader, ctrl_reset, hover_hint

from lane import Lane


def num_font(size):
    """Light numerals (Urbanist Light / Segoe UI Light) for the big figures."""
    return ctk.CTkFont(family=theme.lux_numeral_family(), size=size)


def label(parent, text, **kw):
    """An uppercase peach label (JAMM Lux: wide-set, never clickable on its own)."""
    return ctk.CTkLabel(parent, text=text.upper(), font=font(11, "bold"), text_color=ACCENT_SOFT, **kw)


def lux_semis(semis):
    if not semis:
        return "0 st"
    return f"{'+' if semis > 0 else '−'}{abs(semis)} st"


def glow_image(w, h):
    """The hero's stage light: a soft orange glow from the top left fading into ink."""
    import numpy as np
    from PIL import Image, ImageTk
    sw, sh = max(2, w // 8), max(2, h // 8)
    x = (np.arange(sw)[None, :] / sw - 0.12) / 0.6
    y = (np.arange(sh)[:, None] / sh) / 1.4
    k = np.clip(1 - np.sqrt(x * x + y * y), 0, 1) ** 1.6 * 0.20
    bg = np.array([0x0d, 0x0d, 0x0d], float)
    glow = np.array([0xfe, 0x8b, 0x48], float)
    img = (bg + (glow - bg) * k[..., None]).astype("uint8")
    return ImageTk.PhotoImage(Image.fromarray(img, "RGB").resize((w, h), Image.BICUBIC))


class LuxLayoutMixin:
    """Lux layout (part of App)."""

    def _build_ui_lux(self):
        self.root.configure(fg_color=BG)
        self._build_header_lux()
        main = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        main.grid(row=1, column=0, sticky="nsew", padx=32, pady=(0, 18))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        self._build_hero(main)

        left = ctk.CTkFrame(main, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        self._build_dropzone(left)
        self._build_tracks_lux(left)
        self._build_tune(main)
        # the master fader works as before but isn't shown: Lux has a master slider in the transport
        self._fader_home = ctk.CTkFrame(self.root, fg_color=BG)
        self.fader = MasterFader(self, self._fader_home)
        self._build_transport(main)

    # ----- header -----
    def _build_header_lux(self):
        bar = ctk.CTkFrame(self.root, fg_color=HEADER, corner_radius=0, height=72)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, padx=32, pady=16, sticky="w")
        ctk.CTkLabel(left, text="NiSH", font=ctk.CTkFont(family=theme.lux_display_family(), size=20,
                                                         weight="bold"), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(left, text=" Player", font=num_font(20), text_color=MUTED).pack(side="left")
        self.song_sep = ctk.CTkLabel(left, text="      ", font=font(13), text_color=MUTED)
        self.song_lbl = ctk.CTkLabel(left, text="", font=font(13), text_color=MUTED)
        self.status = ctk.CTkLabel(bar, text="", font=font(12), text_color=AMBER_TXT)
        self.status.grid(row=0, column=1, sticky="e", padx=12)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, padx=32, pady=14, sticky="e")

        def quiet(parent, text, cmd, **kw):     # peach text, no fill (JAMM Lux "quiet" button)
            return ctk.CTkButton(parent, text=text, command=cmd, height=40, corner_radius=20,
                                 fg_color="transparent", hover_color=BTN_HOVER, text_color=ACCENT_SOFT,
                                 font=font(13, "bold"), **kw)
        openbox = ctk.CTkFrame(right, fg_color="transparent")
        openbox.pack(side="left")
        self.open_btn = quiet(openbox, "Open", self.open_dialog, width=64)
        self.open_btn.pack(side="left")
        self.recent_btn = ctk.CTkButton(openbox, text="", image=icon("chevron", ACCENT_SOFT, 12), width=28,
                                        height=40, corner_radius=14, fg_color="transparent",
                                        hover_color=BTN_HOVER, command=self.open_recent)
        self.recent_btn.pack(side="left")
        self.save_btn = quiet(right, "Save", lambda: self.save_project(), width=60)
        self.save_btn.pack(side="left", padx=(4, 12))
        self.split_btn = ctk.CTkButton(right, text="Split song", image=icon("plus", TEXT, 14), compound="left",
                                       command=self.open_split, height=44, corner_radius=22, width=0,
                                       fg_color=BTN, hover_color=BTN_HOVER, text_color=TEXT,
                                       font=font(14, "bold"))
        self.split_btn.pack(side="left", padx=4)
        self.export_btn = ctk.CTkButton(right, text="Export", image=icon("export", TEXT, 15), compound="left",
                                        command=self.open_export, height=44, corner_radius=22, width=0,
                                        fg_color="transparent", hover_color=BTN_HOVER, text_color=TEXT,
                                        border_width=1, border_color=CONTROL, font=font(14, "bold"))
        self.export_btn.pack(side="left", padx=4)
        self.cog_btn = ctk.CTkButton(right, text="", image=icon("cog", TEXT2, 20), width=44, height=44,
                                     corner_radius=22, fg_color="transparent", hover_color=BTN_HOVER,
                                     command=self.open_settings)
        self.cog_btn.pack(side="left", padx=(8, 0))
        for b, tip in ((self.open_btn, "Open project  ·  Ctrl+O"), (self.save_btn, "Save project  ·  Ctrl+S"),
                       (self.split_btn, "Split a song from YouTube or a file"),
                       (self.export_btn, "Export the mix or each track"), (self.cog_btn, "Settings and updates")):
            hover_hint(b, tip)
        self.settings_pop = None
        self._style_cog()
        ctk.CTkFrame(self.root, fg_color=SEPARATOR, height=1, corner_radius=0).grid(row=0, column=0, sticky="sew")

    # ----- song header -----
    def _build_hero(self, parent):
        c = self.hero = tk.Canvas(parent, height=168, bg=BG, highlightthickness=0)
        c.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 0), pady=(0, 8))
        # stretch the canvas over the whole width (the glow starts at the window's edge)
        c.grid_configure(padx=(0, 0))
        self.hero_title = c        # (the old name: "is the Lux header there?")
        self._hero = {"kicker": "NO TRACKS YET", "title": "Drop a song to begin", "artist": "",
                      "Length": "–", "Key": "–"}
        self._hero_img = None
        c.bind("<Configure>", lambda e: self._draw_hero())

    def _draw_hero(self):
        c = self.hero
        try:
            w, h = c.winfo_width(), c.winfo_height()
        except tk.TclError:
            return
        if w < 50:
            return
        c.delete("all")
        try:
            self._hero_img = glow_image(w, h)
            c.create_image(0, 0, image=self._hero_img, anchor="nw")
        except Exception:
            pass
        v = self._hero
        disp = theme.lux_display_family()
        c.create_text(0, 44, text=v["kicker"], anchor="w", fill=ACCENT_SOFT, font=(theme.UI, 9, "bold"))
        c.create_text(0, 92, text=v["title"], anchor="w", fill=TEXT, font=(disp, 34, "bold"))
        c.create_text(0, 136, text=v["artist"], anchor="w", fill=TEXT2, font=(theme.UI, 12))
        x = w
        for key in ("Key", "Length"):                  # laid out from the right: Length | Key
            val_w = c.tk.call("font", "measure", (theme.lux_numeral_family(), 22), v[key])
            lab_w = c.tk.call("font", "measure", (theme.UI, 9, "bold"), key.upper())
            col = max(val_w, lab_w)
            c.create_text(x - col, 104, text=key.upper(), anchor="w", fill=ACCENT_SOFT, font=(theme.UI, 9, "bold"))
            c.create_text(x - col, 132, text=v[key], anchor="w", fill=TEXT, font=(theme.lux_numeral_family(), 22))
            x -= col + 40

    def _update_hero(self):
        c = getattr(self, "hero_title", None)
        try:
            if c is None or not c.winfo_exists():
                return
        except tk.TclError:
            return
        v = self._hero
        if self.lanes:
            name = (engine.song_name([lane.track.path for lane in self.lanes]) or "").lstrip("~").strip()
            artist, _, title = name.partition(" - ")
            if not title:
                artist, title = "", name
            n = len(self.lanes)
            v["kicker"] = f"NOW PLAYING  ·  {n} TRACK{'S' if n > 1 else ''}"
            v["title"], v["artist"] = title or "Untitled", artist
            v["Length"] = fmt_time(self.player.length() / engine.SR) if self.player.length() else "–"
        else:
            v.update(kicker="NO TRACKS YET", title="Drop a song to begin",
                     artist="Or click Split song to get one from YouTube.", Length="–")
        v["Key"] = self._lux_key()
        self._draw_hero()

    def _lux_key(self):
        """The song's key (found once per set of tracks, in the background), moved with the pitch."""
        import keydetect
        if not self.lanes:
            return "–"
        paths = tuple(sorted(lane.track.path for lane in self.lanes))
        if getattr(self, "_key_for", None) != paths:
            self._key_for, self._key = paths, None
            tracks = [lane.track for lane in self.lanes]

            def work():
                k = keydetect.song_key(tracks)
                self.root.after(0, lambda: (setattr(self, "_key", k) if self._key_for == paths else None,
                                            self._update_hero()))
            import threading
            threading.Thread(target=work, daemon=True).start()
        if self._key is None:
            return "…"
        if self._key == "":
            return "–"
        return keydetect.transpose(self._key, self.semis)

    # ----- tracks -----
    def _build_tracks_lux(self, parent):
        box = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        box.grid(row=1, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)
        box.grid_rowconfigure(1, weight=1)
        ruler = ctk.CTkFrame(box, fg_color=BG, height=34, corner_radius=0)
        ruler.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ruler.grid_columnconfigure(1, weight=1)
        cnt = ctk.CTkFrame(ruler, fg_color="transparent", width=Lane.LUX_HEAD_W + Lane.LUX_INSET - 16, height=34)
        cnt.grid(row=0, column=0, padx=(14, 2))
        cnt.grid_propagate(False)
        cnt.grid_columnconfigure(0, weight=1)
        cnt.grid_rowconfigure(0, weight=1)
        self.count_lbl = ctk.CTkLabel(cnt, text="NO TRACKS", font=font(11, "bold"), text_color=ACCENT_SOFT,
                                      anchor="w")
        self.count_lbl.grid(row=0, column=0, sticky="w")
        self.compact_btn = ctk.CTkButton(cnt, text="", width=28, height=24, corner_radius=12, border_width=0,
                                         command=self.toggle_compact)
        self.compact_btn.grid(row=0, column=1, padx=(0, 4))
        self._style_compact()
        self.ruler = tk.Canvas(ruler, height=30, bg=BG, highlightthickness=0, cursor="xterm")
        self.ruler.grid(row=0, column=1, sticky="ew", padx=(0, Lane.LUX_INSET + 8))
        self.ruler.bind("<Configure>", lambda e: self.draw_ruler())
        self.ruler.bind("<Button-1>", self._ruler_press)
        self.ruler.bind("<B1-Motion>", self._ruler_drag)
        self.ruler.bind("<ButtonRelease-1>", self._ruler_release)
        self.ruler.bind("<Double-Button-1>", self._ruler_double)
        self.ruler.bind("<Motion>", self._ruler_hover)
        self._rdrag = None
        self.lanes_box = ctk.CTkScrollableFrame(box, fg_color=BG, corner_radius=0,
                                                scrollbar_button_color=BORDER2,
                                                scrollbar_button_hover_color=CONTROL2)
        self.lanes_box.grid(row=1, column=0, sticky="nsew")
        self.lanes_box._parent_canvas.bind("<Configure>", lambda e: self._fit_scrollbar(), add="+")
        self.lanes_box.bind("<Configure>", lambda e: self._fit_scrollbar(), add="+")
        self.lanes_box.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(self.lanes_box, font=font(14), text_color=MUTED, justify="center",
                                  text="No tracks yet.\nDrop a song, a karaoke file or a set of stems "
                                       "anywhere — or click Open")

    # ----- speed & pitch panel -----
    def _build_tune(self, parent):
        p = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=20, width=340)
        p.grid(row=1, column=1, sticky="ns", padx=(24, 0), pady=(40, 0))
        p.grid_propagate(False)
        p.pack_propagate(False)
        inner = ctk.CTkFrame(p, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=24, pady=22)

        def block(title, lo, hi, steps, value, command, big=40):
            top = ctk.CTkFrame(inner, fg_color="transparent")
            top.pack(fill="x")
            label(top, title).pack(side="left", anchor="s", pady=(0, 8))
            val = ctk.CTkLabel(top, text="", font=num_font(big), text_color=TEXT)
            val.pack(side="right")
            sl = ctk.CTkSlider(inner, from_=lo, to=hi, number_of_steps=steps, height=18, command=command,
                               progress_color=TEXT, button_color=TEXT, button_hover_color=ACCENT_STRONG,
                               fg_color=BORDER2)
            sl.set(value)
            sl.pack(fill="x", pady=(6, 22))
            return val, sl

        self.speed_val, self.speed_slider = block("Speed", 0.5, 1.5, 20, 1.0, self.on_speed)
        self.pitch_val, self.pitch_slider = block("Pitch", -6, 6, 12, 0, self.on_pitch)
        ctk.CTkFrame(inner, fg_color=SEPARATOR, height=1, corner_radius=0).pack(fill="x", pady=(0, 18))

        self.fine_card = fc = ctk.CTkFrame(inner, fg_color="transparent")
        fc.pack(fill="x")
        top = ctk.CTkFrame(fc, fg_color="transparent")
        top.pack(fill="x")
        label(top, "Fine tune").pack(side="left", anchor="s", pady=(0, 6))
        self.fine_val = ctk.CTkLabel(top, text="0 ct", font=num_font(26), anchor="e")
        self.fine_val.pack(side="right")
        self.fine_slider = ctk.CTkSlider(fc, from_=-50, to=50, number_of_steps=100, height=18,
                                         command=self.on_fine)
        self.fine_slider.set(0)
        self.fine_slider.pack(fill="x", pady=(6, 16))
        self.fine_scale = ctk.CTkFrame(fc, fg_color="transparent")       # (Dark/Light: the ±50 marks)
        row = ctk.CTkFrame(fc, fg_color="transparent")
        row.pack(fill="x")
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_chk = ForkSwitch(row, "Auto 440", self.auto_var, self.on_auto)
        self.auto_chk.pack(side="left")
        ctk.CTkLabel(row, text=" BETA ", font=font(9, "bold"), text_color=ACCENT_SOFT, fg_color="transparent",
                     corner_radius=8, height=20).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(fc, text="Tunes to A = 440 Hz and overrides fine tune.", font=font(12), text_color=MUTED,
                     anchor="w", justify="left", wraplength=288).pack(fill="x", pady=(8, 0))
        ctrl_reset(self.speed_slider, 1.0, self.on_speed)
        ctrl_reset(self.pitch_slider, 0, self.on_pitch)
        ctrl_reset(self.fine_slider, 0, self.on_fine)
        self._style_fine()

        bottom = ctk.CTkFrame(inner, fg_color="transparent")
        bottom.pack(side="bottom", fill="x")
        self.busy_lbl = ctk.CTkLabel(bottom, text="", font=font(12), text_color=ACCENT_SOFT, compound="left",
                                     anchor="w", justify="left", wraplength=288)
        self.busy_lbl.pack(fill="x")
        self.reset_btn = ctk.CTkButton(bottom, text="Reset speed & pitch", width=0, height=40, corner_radius=20,
                                       font=font(13, "bold"), fg_color="transparent", hover_color=BTN_HOVER,
                                       border_width=0, text_color=ACCENT_SOFT, command=self.reset_stretch)
        self.reset_btn.pack(anchor="w", pady=(6, 0))

    # ----- transport: one pill at the bottom -----
    def _build_transport(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=DECK, corner_radius=40, border_width=1, border_color=BORDER2)
        bar.grid(row=2, column=0, columnspan=2, pady=(16, 0))
        tr = ctk.CTkFrame(bar, fg_color="transparent")
        tr.pack(padx=(10, 28), pady=7)
        back = RoundButton(tr, text="", image=icon("back", TEXT, 16), width=44, height=44, corner_radius=22,
                           fg_color=BTN, hover_color=BTN_HOVER, border_width=0, text_color=TEXT,
                           command=lambda: self.seek(0))
        back.grid(row=0, column=0, padx=(2, 6))
        hover_hint(back, "Back to the start  ·  Home")
        self.play_ring = self._ring(tr, 60)
        self.play_ring.grid(row=0, column=1, padx=2)
        self.play_btn = RoundButton(self.play_ring, text="", image=icon("play", ACTION_TXT, 24), width=60,
                                    height=60, corner_radius=30, fg_color=ACTION, hover_color=ACTION_HOVER,
                                    text_color=ACTION_TXT, command=self.toggle_play)
        self.play_btn.place(relx=0.5, rely=0.5, anchor="center")
        hover_hint(self.play_btn, "Play / Pause  ·  Space")
        self.loop_btn = RoundButton(tr, text="", width=44, height=44, corner_radius=22, border_width=0,
                                    command=self.toggle_loop)
        self.loop_btn.grid(row=0, column=2, padx=6)
        hover_hint(self.loop_btn, "Loop the marked area  ·  L")
        fade = self.fade_box = ctk.CTkFrame(tr, fg_color="transparent", width=160, height=44)
        fade.grid(row=0, column=3, padx=(4, 0))
        fade.grid_propagate(False)
        fade.pack_propagate(False)
        self.fade_inner = ctk.CTkFrame(fade, fg_color="transparent")
        ctk.CTkLabel(self.fade_inner, text="Fade", font=font(12), text_color=MUTED, width=34).pack(side="left")
        self.fade_slider = ctk.CTkSlider(self.fade_inner, from_=0, to=2, number_of_steps=20, width=76, height=16,
                                         command=self.on_fade, progress_color=ACCENT, button_color=ACCENT,
                                         button_hover_color=ACCENT_HOVER, fg_color=ACCENT_TRACK)
        self.fade_slider.set(engine.LOOP_FADE)
        self.fade_slider.pack(side="left", padx=4)
        self.fade_val = ctk.CTkLabel(self.fade_inner, text="1.0 s", font=font(12), text_color=ACCENT_SOFT,
                                     width=40, anchor="w")
        self.fade_val.pack(side="left")
        ctrl_reset(self.fade_slider, engine.LOOP_FADE, self.on_fade)
        self.time_lbl = ctk.CTkLabel(tr, text="0:00 / 0:00", font=num_font(28), text_color=TEXT, anchor="w")
        self.time_lbl.grid(row=0, column=4, padx=(16, 24))
        # master volume (the hidden fader does the work, and its meters keep running)
        ctk.CTkFrame(tr, fg_color=SEPARATOR, width=1, height=32, corner_radius=0).grid(row=0, column=5,
                                                                                          padx=(0, 16))
        label(tr, "Master").grid(row=0, column=6, padx=(0, 10))
        self.master_slider = ctk.CTkSlider(tr, from_=0, to=1, width=110, height=16, command=self.fader.set_pos,
                                           progress_color=TEXT, button_color=TEXT,
                                           button_hover_color=ACCENT_STRONG, fg_color=BORDER2)
        self.master_slider.grid(row=0, column=7)
        self.master_db = ctk.CTkLabel(tr, text="0.0 dB", font=font(12), text_color=MUTED, width=64, anchor="e")
        self.master_db.grid(row=0, column=8)

        def follow(pos):
            self.master_slider.set(pos)
            self.master_db.configure(text=self.fader.db_lbl.cget("text"))
        self.fader.on_change = follow
        follow(self.fader.pos)
        ctrl_reset(self.master_slider, self.fader.pos, self.fader.set_pos)
        self._style_loop()
