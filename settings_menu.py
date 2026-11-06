"""The cogwheel menu in the top right: version, theme, and updates.

Two kinds of update, both manual:
- a YouTube fix (ytpack.py): a ~3 MB pack with a newer yt-dlp. It installs while the app runs and is
  used from the next YouTube download - no restart.
- a new version of the app: the full download, installed by closing and restarting (updater.py).
When both are new, the quick YouTube fix comes first. If YouTube extraction fails five times on one
day, the cogwheel turns amber and this menu suggests checking for an update.
"""
import threading
import traceback
import webbrowser

import customtkinter as ctk

import engine
import settings
import theme
import updater
import ytpack
from theme import *  # noqa: F401,F403



class SettingsMenu:
    W = 320

    def __init__(self, app, anchor):
        self.app = app
        self.root = app.root
        self.anchor = anchor
        self.state = "idle"   # idle, checking, latest, newer, downloading, preparing, ready, installing, error
        self.release = None
        self.error = ""
        self.fraction = 0.0
        self.cancel = False
        self.stage = None
        # the YouTube fix: None (nothing new), newer, installing, installed, error
        self.yt = {"state": None, "info": None, "fraction": 0.0, "error": "", "cancel": False}
        ready = updater.staged_update()    # downloaded earlier but not installed yet
        if ready:
            self.stage, tag = ready
            self.state, self.release = "ready", {"tag": tag}
        f = self.frame = ctk.CTkFrame(self.root, fg_color=POPOVER, border_color=BORDER_POP, border_width=1,
                                      corner_radius=14, width=self.W)
        ctk.CTkFrame(f, fg_color="transparent", width=self.W, height=1).pack(side="bottom")  # fixed width
        head = ctk.CTkFrame(f, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 2))
        ctk.CTkLabel(head, text="NiSH Player", font=font(15, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkButton(head, text="", image=icon("close", MUTED, 13), width=28, height=28, fg_color="transparent",
                      hover_color=BTN_HOVER, command=self.close).pack(side="right")
        self.version_lbl = ctk.CTkLabel(f, text="", font=font(12), text_color=MUTED, anchor="w", justify="left")
        self.version_lbl.pack(fill="x", padx=18)
        # Theme: dark by default; the choice is remembered
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(12, 0))
        ctk.CTkLabel(row, text="Theme", font=font(13), text_color=TEXT, anchor="w").pack(side="left")
        dark = theme.MODE == "dark"
        self.theme_btn = ToolButton(row, "Dark" if dark else "Light", self.toggle_theme, height=30, width=92,
                                    image=icon("moon" if dark else "sun", ACCENT_SOFT, 15), compound="left",
                                    font=font(12))
        self.theme_btn.pack(side="right")
        self.notice = ctk.CTkFrame(f, fg_color=AMBER_BG, border_color=AMBER_BORDER, border_width=1, corner_radius=8)
        self.notice_lbl = ctk.CTkLabel(self.notice, text="", font=font(12), text_color=AMBER_TXT, justify="left",
                                       anchor="w", wraplength=self.W - 60)
        self.notice_lbl.pack(fill="x", padx=12, pady=8)
        self.sep = ctk.CTkFrame(f, fg_color=BORDER, height=1, corner_radius=0)
        self.sep.pack(fill="x", padx=18, pady=(12, 0))
        self.upd = ctk.CTkFrame(f, fg_color="transparent")
        self.upd.pack(fill="x", padx=18, pady=(10, 16))
        self.yt_msg = ctk.CTkLabel(self.upd, text="", font=font(12), text_color=SOFT, anchor="w", justify="left",
                                   wraplength=self.W - 40, compound="left")
        self.yt_bar = ctk.CTkProgressBar(self.upd, height=6, progress_color=ACCENT, fg_color=BORDER2)
        self.yt_btn = ToolButton(self.upd, "Install YouTube fix", self.on_yt_button, height=36)
        self.msg = ctk.CTkLabel(self.upd, text="", font=font(12), text_color=SOFT, anchor="w", justify="left",
                                wraplength=self.W - 40, compound="left")
        self.bar = ctk.CTkProgressBar(self.upd, height=6, progress_color=ACCENT, fg_color=BORDER2)
        self.btn = ToolButton(self.upd, "Check for updates", self.on_button, height=36)
        f.bind("<Escape>", lambda e: self.close())
        self.refresh()
        self.place()

    def toggle_theme(self):
        self.app.apply_theme("light" if theme.MODE == "dark" else "dark")

    # ----- popover -----
    def place(self):
        r = self.root
        r.update_idletasks()
        if not self.is_open():
            self.frame.place(x=-2000, y=0)  # measure first: the popover is as wide as its content
            r.update_idletasks()
        w = self.frame.winfo_reqwidth()
        x = self.anchor.winfo_rootx() - r.winfo_rootx() + self.anchor.winfo_width() - w
        y = self.anchor.winfo_rooty() - r.winfo_rooty() + self.anchor.winfo_height() + 8
        self.frame.place(x=max(12, x), y=y)
        self.frame.lift()

    def is_open(self):
        return bool(self.frame.winfo_exists() and self.frame.winfo_ismapped())

    def close(self):
        self.frame.place_forget()

    # ----- state -----
    def refresh(self):
        n = settings.yt_failures_today()
        if settings.suggest_update():
            self.notice_lbl.configure(text=f"YouTube downloads have failed {n} times today. "
                                           "Checking for an update may fix this.")
            self.notice.pack(fill="x", padx=18, pady=(10, 0), before=self.sep)
        else:
            self.notice.pack_forget()
        yv = ytpack.version()
        self.version_lbl.configure(text="Version " + updater.version_text()
                                   + (f"\nYouTube support {yv}" if yv else ""))
        for w in (self.yt_msg, self.yt_bar, self.yt_btn, self.msg, self.bar, self.btn):
            w.pack_forget()
        yt = self._refresh_yt()
        st, rel = self.state, self.release
        primary = False
        if st == "latest" and yt in ("newer", "installing", "installed", "error"):
            # nothing new for the app: the YouTube fix says it all (and "Check again" stays below it)
            btn = None if yt in ("newer", "installing", "error") else "Check again"
            self._button(self.btn, btn, False)
            return
        if st == "idle":
            btn = "Check for updates"
        elif st == "checking":
            self._msg("Checking for updates…", spin=True)
            btn = None
        elif st == "latest":
            self._msg("You have the latest version.", ok=True)
            btn = "Check again"
        elif st == "newer":
            size = f" ({rel['size'] / 1e6:.0f} MB)" if rel.get("size") else ""
            also = " also" if yt in ("newer", "installing") else ""
            self._msg(f"Version {updater.version_text(rel['tag'])} is{also} available{size}.")
            if updater.can_update():
                btn, primary = "Download", not also      # the quick YouTube fix comes first
            else:
                btn = "Open download page"
        elif st == "downloading":
            self._msg(f"Downloading… {int(self.fraction * 100)}%", spin=True)
            self.bar.set(self.fraction)
            self.bar.pack(fill="x", pady=(0, 10))
            btn = "Cancel"
        elif st == "preparing":
            self._msg("Unpacking the download…", spin=True)
            btn = None
        elif st == "ready":
            self._msg(f"Version {updater.version_text(rel['tag'])} is downloaded and ready to install. "
                      "NiSH Player will close, update and start again.")
            self.msg.configure(text_color=GREEN_TXT)
            btn, primary = "Close and update", True
        elif st == "installing":
            self._msg("Closing and updating…", spin=True)
            btn = None
        else:
            self._msg(self.error or "Something went wrong.", warn=True)
            btn = "Try again"
        self._button(self.btn, btn, primary)

    def _refresh_yt(self):
        """The YouTube fix's message and button (above the app's). Returns its state."""
        y = self.yt
        st = y["state"]
        if st == "newer":
            size = f" ({y['info']['size'] / 1e6:.0f} MB)" if y["info"].get("size") else ""
            self._msg(f"A YouTube fix is available{size}. It installs in seconds, no restart.", label=self.yt_msg)
            self._button(self.yt_btn, "Install YouTube fix", True)
        elif st == "installing":
            if y["fraction"] < 1:
                text = f"Installing the YouTube fix… {int(y['fraction'] * 100)}%"
            else:
                text = "Checking the YouTube fix…"
            self._msg(text, spin=True, label=self.yt_msg)
            self.yt_bar.set(y["fraction"])
            self.yt_bar.pack(fill="x", pady=(0, 10))
            if y["fraction"] < 1:
                self._button(self.yt_btn, "Cancel", False)
        elif st == "installed":
            self._msg("YouTube fix installed. It's used from the next YouTube download.", ok=True, label=self.yt_msg)
        elif st == "error":
            self._msg(y["error"] or "The YouTube fix couldn't be installed.", warn=True, label=self.yt_msg)
            self._button(self.yt_btn, "Try again", False)
        if st in ("installed", "error") and self.state not in ("latest",):
            self.yt_msg.pack_configure(pady=(0, 12))
        return st

    def _button(self, b, text, primary):
        if not text:
            return
        b.configure(text=text, fg_color=ACCENT if primary else BTN, hover_color=ACCENT_HOVER if primary else BTN_HOVER,
                    text_color=ACCENT_TXT if primary else TEXT2, border_width=0 if primary else 1,
                    font=font(13, "bold") if primary else font(13))
        b.pack(fill="x", pady=(0, 10) if b is self.yt_btn else 0)

    def _msg(self, text, spin=False, ok=False, warn=False, label=None):
        if spin:
            frame = (int(self.root.tk.call("clock", "milliseconds")) // 90) % 12
            img, col = icon(f"spin{frame}", ACCENT_SOFT, 14), SOFT
        elif ok:
            img, col = icon("check", GREEN, 14), GREEN_TXT
        elif warn:
            img, col = icon("warn", AMBER, 14), AMBER_TXT
        else:
            img, col = None, SOFT
        lbl = label or self.msg
        lbl.configure(text=("  " if img else "") + text, text_color=col)
        if img:
            lbl.configure(image=img)
        else:
            no_image(lbl)
        lbl.pack(fill="x", pady=(0, 10))
        if spin:
            self.root.after(90, self._spin_tick)

    def _spin_tick(self):
        if self.frame.winfo_exists() and (self.state in ("checking", "downloading", "preparing", "installing")
                                          or self.yt["state"] == "installing"):
            self.refresh()

    def _set(self, state, **kw):
        self.state = state
        for k, v in kw.items():
            setattr(self, k, v)
        self.app.events.put(("settings_refresh",))

    # ----- actions -----
    def on_button(self):
        st = self.state
        if st in ("idle", "latest", "error"):
            self.start_check()
        elif st == "newer":
            if updater.can_update():
                self.start_download()
            else:
                webbrowser.open(updater.PAGE)
        elif st == "downloading":
            self.cancel = True
        elif st == "ready":
            self.state = "installing"
            self.refresh()
            self.app.install_update(self.stage)

    def start_check(self):
        self.state = "checking"
        if self.yt["state"] in ("installed", "error"):
            self.yt["state"] = None
        self.refresh()

        def work():
            try:
                pack = ytpack.check()
                yt_new = pack if pack["newer"] else None
            except Exception:
                traceback.print_exc()          # no YouTube fix published (yet), or offline: just the app check
                yt_new = None
            if self.yt["state"] in (None, "installed", "error") or yt_new:
                self.yt.update(state="newer" if yt_new else None, info=yt_new, error="")
            try:
                rel = updater.check()
                if not rel["url"] and rel["newer"]:
                    raise RuntimeError("The latest release has no Windows download yet. Try again later.")
                self._set("newer" if rel["newer"] else "latest", release=rel)
            except Exception as e:
                traceback.print_exc()
                msg = str(e) if isinstance(e, RuntimeError) else "Couldn't reach GitHub. Check your connection."
                self._set("error", error=msg)

        threading.Thread(target=work, daemon=True).start()

    def start_download(self):
        self.cancel = False
        self.fraction = 0.0
        self.state = "downloading"
        self.refresh()
        rel = self.release

        def work():
            zpath = engine.DATA_DIR / "update" / updater.ASSET
            try:
                updater.download(rel["url"], zpath, progress=lambda f: self._set("downloading", fraction=f),
                                 cancelled=lambda: self.cancel)
                self._set("preparing")
                stage = updater.unpack(zpath)
                try:
                    zpath.unlink()
                except OSError:
                    pass
                self._set("ready", stage=stage)     # the user decides when to close and update
            except Exception as e:
                traceback.print_exc()
                if self.cancel:
                    self._set("newer")
                else:
                    self._set("error", error="The update couldn't be downloaded. " + (str(e)[:120] or ""))

        threading.Thread(target=work, daemon=True).start()

    def on_yt_button(self):
        st = self.yt["state"]
        if st in ("newer", "error"):
            self.start_yt_install()
        elif st == "installing":
            self.yt["cancel"] = True

    def start_yt_install(self):
        y = self.yt
        info = y["info"]
        y.update(state="installing", fraction=0.0, cancel=False, error="")
        self.refresh()

        def progress(f):
            y["fraction"] = min(f, 0.99)
            self.app.events.put(("settings_refresh",))

        def checking():
            y["fraction"] = 1.0
            self.app.events.put(("settings_refresh",))

        def work():
            try:
                ytpack.install(info, progress=progress, cancelled=lambda: y["cancel"], checking=checking)
                y.update(state="installed", fraction=1.0)
                self.app.events.put(("yt_fix_installed",))
            except Exception as e:
                traceback.print_exc()
                if y["cancel"]:
                    y.update(state="newer")
                else:
                    msg = str(e) if isinstance(e, RuntimeError) else "Couldn't reach GitHub. Check your connection."
                    y.update(state="error", error=msg.split("\n")[0])
            self.app.events.put(("settings_refresh",))

        threading.Thread(target=work, daemon=True).start()
