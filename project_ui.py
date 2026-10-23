"""Projects in the main window: open / save / recent list (the ▾ under Open…) and the window title."""
import os
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import engine
import project
from engine import APP_NAME
from theme import *  # noqa: F401,F403



def short_folder(path, n=40):
    """'Music\\My Song stems' – the last two folder names, shortened if long."""
    parts = Path(path).parent.parts
    text = os.sep.join(parts[-2:]) if len(parts) >= 2 else str(Path(path).parent)
    return text if len(text) <= n else "…" + text[-(n - 1):]


class RecentMenu:
    W = 360

    def __init__(self, app, anchor):
        self.app, self.root, self.anchor = app, app.root, anchor
        f = self.frame = ctk.CTkFrame(self.root, fg_color=POPOVER, border_color=BORDER_POP, border_width=1,
                                      corner_radius=14, width=self.W)
        ctk.CTkFrame(f, fg_color="transparent", width=self.W, height=1).pack(side="bottom")  # fixed width
        ctk.CTkLabel(f, text="RECENT PROJECTS", font=font(11), text_color=MUTED, anchor="w").pack(
            fill="x", padx=18, pady=(12, 4))
        self.rows = []
        items = project.recent()
        if not items:
            ctk.CTkLabel(f, text="No saved projects yet. Save one with Save… (Ctrl+S); YouTube imports\n"
                                 "with stems save one automatically.", font=font(12), text_color=MUTED,
                         justify="left", anchor="w").pack(fill="x", padx=18, pady=(2, 14))
        for p in items:
            self._row(p)
        if items:
            ctk.CTkFrame(f, fg_color="transparent", height=8).pack()
        f.bind("<Escape>", lambda e: self.close())
        self.place()

    def _row(self, path):
        row = ctk.CTkFrame(self.frame, fg_color="transparent", corner_radius=8, cursor="hand2")
        row.pack(fill="x", padx=8, pady=1)
        ic = ctk.CTkLabel(row, text="", image=icon("project", ACCENT_SOFT, 18), width=22)
        ic.pack(side="left", padx=(10, 8), pady=6)
        txt = ctk.CTkFrame(row, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True, pady=4)
        current = self.app.project_path and Path(self.app.project_path).resolve() == Path(path).resolve()
        name = ctk.CTkLabel(txt, text=Path(path).stem + ("  (open)" if current else ""), font=font(13, "bold"),
                            text_color=TEXT, anchor="w", height=18)
        name.pack(fill="x")
        sub = ctk.CTkLabel(txt, text=short_folder(path), font=font(11), text_color=MUTED, anchor="w", height=16)
        sub.pack(fill="x")
        for w in (row, ic, txt, name, sub):
            w.bind("<Button-1>", lambda e, p=path: self.pick(p))
            w.bind("<Enter>", lambda e, r=row: r.configure(fg_color=BTN_HOVER))
            w.bind("<Leave>", lambda e, r=row: r.configure(fg_color="transparent"))
        self.rows.append((path, row))

    def pick(self, path):
        self.close()
        self.app.open_project(path)

    def place(self):
        r = self.root
        r.update_idletasks()
        x = self.anchor.winfo_rootx() - r.winfo_rootx()
        y = self.anchor.winfo_rooty() - r.winfo_rooty() + self.anchor.winfo_height() + 8
        self.frame.place(x=max(12, min(x, r.winfo_width() - self.W - 12)), y=y)
        self.frame.lift()

    def is_open(self):
        return bool(self.frame.winfo_exists() and self.frame.winfo_ismapped())

    def close(self):
        if self.frame.winfo_exists():
            self.frame.place_forget()


class ProjectMixin:
    """Open / save projects and the window title (part of App)."""

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
        if self.recent_pop is not None and self.recent_pop.frame.winfo_exists() and self.recent_pop.is_open():
            self.recent_pop.close()
            return
        if self.recent_pop is not None and self.recent_pop.frame.winfo_exists():
            self.recent_pop.frame.destroy()
        self.recent_pop = RecentMenu(self, self.open_btn)
