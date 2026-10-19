"""The ▾ list under Open…: the projects you saved or opened most recently."""
import os
from pathlib import Path

import customtkinter as ctk

import project
from theme import *  # noqa: F401,F403

POP_BG, POP_BORDER, ROW_HOVER = "#1a1d22", "#343a42", "#232830"


def short_folder(path, n=40):
    """'Music\\My Song stems' – the last two folder names, shortened if long."""
    parts = Path(path).parent.parts
    text = os.sep.join(parts[-2:]) if len(parts) >= 2 else str(Path(path).parent)
    return text if len(text) <= n else "…" + text[-(n - 1):]


class RecentMenu:
    W = 360

    def __init__(self, app, anchor):
        self.app, self.root, self.anchor = app, app.root, anchor
        f = self.frame = ctk.CTkFrame(self.root, fg_color=POP_BG, border_color=POP_BORDER, border_width=1,
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
            w.bind("<Enter>", lambda e, r=row: r.configure(fg_color=ROW_HOVER))
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
