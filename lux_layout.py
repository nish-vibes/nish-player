"""The Lux main window (the JAMM Lux mockup on the design canvas): a song header with its facts,
the tracks with a speed & pitch panel beside them, and the transport in one bar at the bottom.

Only used in the Lux theme; Dark and Light keep layout.py's window. It builds the same widgets
under the same names (speed_slider, play_btn, lanes_box, ...), so everything else works as is.
"""
import tkinter as tk

import customtkinter as ctk

import engine
import theme
from theme import *  # noqa: F401,F403
from widgets import ForkSwitch, MasterFader, ctrl_reset, hover_hint


def num_font(size):
    """Light numerals (Urbanist Light / Segoe UI Light) for the big figures."""
    return ctk.CTkFont(family=theme.lux_numeral_family(), size=size)


def label(parent, text, **kw):
    """An uppercase peach label (JAMM Lux: wide-set, never clickable on its own)."""
    return ctk.CTkLabel(parent, text=text.upper(), font=font(11, "bold"), text_color=ACCENT_SOFT, **kw)


class LuxLayoutMixin:
    """Lux layout (part of App)."""

    def _build_ui_lux(self):
        self.root.configure(fg_color=BG)
        self._build_header()
        # the song's name lives in the header below, not next to the app name
        hidden = ctk.CTkFrame(self.root)
        self.song_sep = ctk.CTkLabel(hidden, text="")
        self.song_lbl = ctk.CTkLabel(hidden, text="")

        main = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        main.grid(row=1, column=0, sticky="nsew", padx=32, pady=(0, 20))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        self._build_hero(main)

        left = ctk.CTkFrame(main, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        self._build_dropzone(left)
        self._build_tracks(left)

        self._build_tune(main)
        self.fader = MasterFader(self, main)
        self.fader.card.grid(row=1, column=2, sticky="ns", padx=(16, 0))
        self._build_transport(main)

    # ----- song header -----
    def _build_hero(self, parent):
        hero = ctk.CTkFrame(parent, fg_color="transparent")
        hero.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(28, 22))
        hero.grid_columnconfigure(0, weight=1)
        words = ctk.CTkFrame(hero, fg_color="transparent")
        words.grid(row=0, column=0, sticky="sw")
        self.hero_kicker = label(words, "No tracks yet", anchor="w")
        self.hero_kicker.pack(anchor="w")
        self.hero_title = ctk.CTkLabel(words, text="Drop a song to begin", anchor="w",
                                       font=ctk.CTkFont(family=theme.lux_display_family(), size=40,
                                                        weight="bold"), text_color=TEXT)
        self.hero_title.pack(anchor="w", pady=(4, 0))
        self.hero_artist = ctk.CTkLabel(words, text="", font=font(16), text_color=TEXT2, anchor="w")
        self.hero_artist.pack(anchor="w")
        facts = ctk.CTkFrame(hero, fg_color="transparent")
        facts.grid(row=0, column=1, sticky="se")
        self.hero_facts = {}
        for i, key in enumerate(("Length", "Speed", "Pitch")):     # always this order
            box = ctk.CTkFrame(facts, fg_color="transparent")
            box.grid(row=0, column=i, padx=(40 if i else 0, 0), sticky="s")
            label(box, key, anchor="w").pack(anchor="w")
            val = ctk.CTkLabel(box, text="–", font=num_font(26), text_color=TEXT, anchor="w")
            val.pack(anchor="w")
            self.hero_facts[key] = val

    def _update_hero(self):
        try:
            if getattr(self, "hero_title", None) is None or not self.hero_title.winfo_exists():
                return
        except tk.TclError:
            return
        if self.lanes:
            name = engine.song_name([lane.track.path for lane in self.lanes]) or ""
            artist, _, title = name.lstrip("~").strip().partition(" - ")
            if not title:
                artist, title = "", name.lstrip("~").strip()
            n = len(self.lanes)
            self.hero_kicker.configure(text=f"NOW PLAYING · {n} TRACK{'S' if n > 1 else ''}")
            self.hero_title.configure(text=title or "Untitled")
            self.hero_artist.configure(text=artist)
            secs = self.player.length() / engine.SR if self.player.length() else 0
            self.hero_facts["Length"].configure(text=fmt_time(secs))
        else:
            self.hero_kicker.configure(text="NO TRACKS YET")
            self.hero_title.configure(text="Drop a song to begin")
            self.hero_artist.configure(text="Or click Split to get one from YouTube.")
            self.hero_facts["Length"].configure(text="–")
        self.hero_facts["Speed"].configure(text=f"{round(self.speed * 100)}%")
        self.hero_facts["Pitch"].configure(text=lux_semis(self.semis))

    # ----- speed & pitch panel -----
    def _build_tune(self, parent):
        p = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=20, width=320)
        p.grid(row=1, column=1, sticky="ns", padx=(20, 0))
        p.grid_propagate(False)
        p.pack_propagate(False)
        inner = ctk.CTkFrame(p, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=24, pady=22)

        def block(title, lo, hi, steps, value, command, big=40):
            top = ctk.CTkFrame(inner, fg_color="transparent")
            top.pack(fill="x")
            label(top, title).pack(side="left", anchor="s", pady=(0, 6))
            val = ctk.CTkLabel(top, text="", font=num_font(big), text_color=TEXT)
            val.pack(side="right")
            sl = ctk.CTkSlider(inner, from_=lo, to=hi, number_of_steps=steps, height=18, command=command,
                               progress_color=TEXT, button_color=TEXT, button_hover_color=ACCENT_STRONG,
                               fg_color=BORDER2)
            sl.set(value)
            sl.pack(fill="x", pady=(4, 18))
            return val, sl

        self.speed_val, self.speed_slider = block("Speed", 0.5, 1.5, 20, 1.0, self.on_speed)
        self.pitch_val, self.pitch_slider = block("Pitch", -6, 6, 12, 0, self.on_pitch)
        ctk.CTkFrame(inner, fg_color=SEPARATOR, height=1, corner_radius=0).pack(fill="x", pady=(0, 16))

        self.fine_card = fc = ctk.CTkFrame(inner, fg_color="transparent")
        fc.pack(fill="x")
        top = ctk.CTkFrame(fc, fg_color="transparent")
        top.pack(fill="x")
        label(top, "Fine tune").pack(side="left", anchor="s", pady=(0, 4))
        self.fine_val = ctk.CTkLabel(top, text="0 ct", font=num_font(26), anchor="e")
        self.fine_val.pack(side="right")
        self.fine_slider = ctk.CTkSlider(fc, from_=-50, to=50, number_of_steps=100, height=18,
                                         command=self.on_fine)
        self.fine_slider.set(0)
        self.fine_slider.pack(fill="x", pady=(4, 14))
        self.fine_scale = ctk.CTkFrame(fc, fg_color="transparent")       # (Dark/Light: the ±50 marks)
        row = ctk.CTkFrame(fc, fg_color="transparent")
        row.pack(fill="x")
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_chk = ForkSwitch(row, "Auto 440", self.auto_var, self.on_auto)
        self.auto_chk.pack(side="left")
        ctk.CTkLabel(row, text=" BETA ", font=font(9, "bold"), text_color=ACCENT_SOFT, fg_color=CHIP,
                     corner_radius=6, height=18).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(fc, text="Tunes to A = 440 Hz and overrides fine tune. Fine-tuning slightly "
                              "changes the length of the track.", font=font(12), text_color=MUTED,
                     anchor="w", justify="left", wraplength=268).pack(fill="x", pady=(10, 0))
        ctrl_reset(self.speed_slider, 1.0, self.on_speed)
        ctrl_reset(self.pitch_slider, 0, self.on_pitch)
        ctrl_reset(self.fine_slider, 0, self.on_fine)
        self._style_fine()

        bottom = ctk.CTkFrame(inner, fg_color="transparent")
        bottom.pack(side="bottom", fill="x")
        self.busy_lbl = ctk.CTkLabel(bottom, text="", font=font(12), text_color=ACCENT_SOFT, compound="left",
                                     anchor="w", justify="left", wraplength=268)
        self.busy_lbl.pack(fill="x")
        self.reset_btn = ctk.CTkButton(bottom, text="Reset speed & pitch", width=0, height=40, corner_radius=20,
                                       font=font(13, "bold"), fg_color="transparent", hover_color=BTN_HOVER,
                                       border_width=0, text_color=ACCENT_SOFT, command=self.reset_stretch)
        self.reset_btn.pack(anchor="w", pady=(6, 0))

    # ----- transport -----
    def _build_transport(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=DECK, corner_radius=46, border_width=1, border_color=BORDER2)
        bar.grid(row=2, column=0, columnspan=3, pady=(18, 0))
        tr = ctk.CTkFrame(bar, fg_color="transparent")
        tr.pack(padx=(10, 28), pady=6)
        back = RoundButton(tr, text="", image=icon("back", TEXT, 16), width=44, height=44, corner_radius=22,
                           fg_color=BTN, hover_color=BTN_HOVER, border_width=0, text_color=TEXT,
                           command=lambda: self.seek(0))
        back.grid(row=0, column=0, padx=(4, 6))
        hover_hint(back, "Back to the start  ·  Home")
        self.play_ring = self._ring(tr, 64)
        self.play_ring.grid(row=0, column=1, padx=4)
        self.play_btn = RoundButton(self.play_ring, text="", image=icon("play", ACTION_TXT, 26), width=64,
                                    height=64, corner_radius=32, fg_color=ACTION, hover_color=ACTION_HOVER,
                                    text_color=ACTION_TXT, command=self.toggle_play)
        self.play_btn.place(relx=0.5, rely=0.5, anchor="center")
        hover_hint(self.play_btn, "Play / Pause  ·  Space")
        self.loop_btn = RoundButton(tr, text="", width=44, height=44, corner_radius=22, border_width=1,
                                    command=self.toggle_loop)
        self.loop_btn.grid(row=0, column=2, padx=6)
        hover_hint(self.loop_btn, "Loop the marked area  ·  L")
        fade = self.fade_box = ctk.CTkFrame(tr, fg_color="transparent", width=170, height=44)
        fade.grid(row=0, column=3, padx=(12, 0))
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
        self.time_lbl = ctk.CTkLabel(tr, text="0:00 / 0:00", font=num_font(26), text_color=TEXT,
                                     width=170, anchor="w")
        self.time_lbl.grid(row=0, column=4, padx=(12, 0))
        self._style_loop()


def lux_semis(semis):
    if not semis:
        return "0 st"
    return f"{'+' if semis > 0 else '−'}{abs(semis)} st"
