"""The 'Add from YouTube' popover: link, name, karaoke/stems, Auto 440, suffixes, progress."""
import os
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import splitter
import theme
from theme import *  # noqa: F401,F403  (colours follow the light/dark theme)

STEP_TEXT = {"download": "Download the original", "split": "Split with AI", "tune": "Tune to A = 440 Hz",
             "save": "Save the files", "load": "Add to workspace"}


def fmt_dur(sec):
    if not sec:
        return ""
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


class YouTubeJob:
    """Runs one download/split in the background; reports through the app's event queue."""

    def __init__(self, app, source, name, opts):
        self.app, self.source, self.name, self.opts = app, source, name, opts
        self.cancelled = False
        self.running = True
        self.result = self.error = None
        self.progress = {"download": 0.0}  # the first step shows as started straight away
        self.steps = ["download"]
        if opts["karaoke"] or opts["stems"]:
            self.steps.append("split")
        if opts["tune"] and (opts["karaoke"] or opts["stems"] or opts["tuned_original"]):
            self.steps.append("tune")
        if len(self.steps) > 1:
            self.steps.append("save")
        if opts["workspace"]:
            self.steps.append("load")
        threading.Thread(target=self._work, daemon=True).start()

    def check_cancel(self):
        if self.cancelled:
            raise splitter.Cancelled()

    def _work(self):
        try:
            res = splitter.run(self.source, self.name, self.opts,
                               stage=lambda k, f: self.app.events.put(("yt_stage", self, k, f)),
                               check_cancel=self.check_cancel)
            self.app.events.put(("yt_done", self, res, None))
        except splitter.Cancelled:
            self.app.events.put(("yt_done", self, None, "Cancelled."))
        except Exception as e:
            traceback.print_exc()
            msg = str(e).strip().splitlines()[-1] if str(e).strip() else type(e).__name__
            self.app.events.put(("yt_done", self, None, msg))

    def short_status(self):
        words = {"download": "Downloading", "split": "Splitting", "tune": "Tuning", "save": "Saving",
                 "load": "Loading"}
        for k in self.steps:
            f = self.progress.get(k, 0.0)
            if f < 1.0:
                return f"{words[k]} {int(f * 100)}%" if f > 0 else f"{words[k]}…"
        return "Finishing…"

    def status_text(self):
        for k in self.steps:
            f = self.progress.get(k, 0.0)
            if f < 1.0:
                return f"{STEP_TEXT[k]} {int(f * 100)}%"
        return "Finishing…"


class YouTubePopover:
    W = 480

    def __init__(self, app, anchor):
        self.app = app
        self.root = app.root
        self.anchor = anchor
        self.s = splitter.load_settings()
        self.info = None
        self.info_gen = 0
        self._info_job = None
        self.frame = ctk.CTkFrame(self.root, fg_color=POPOVER, border_color=BORDER_POP, border_width=1,
                                  corner_radius=14, width=self.W)
        head = ctk.CTkFrame(self.frame, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(14, 6))
        self.title = ctk.CTkLabel(head, text="Add from YouTube", font=font(16, "bold"), text_color=TEXT)
        self.title.pack(side="left")
        ctk.CTkButton(head, text="", image=icon("close", MUTED, 13), width=30, height=30,
                      fg_color="transparent", hover_color=BTN_HOVER, command=self.close).pack(side="right")
        avail = max(360, self.root.winfo_height() - 150)
        self.body = ctk.CTkScrollableFrame(self.frame, fg_color="transparent", width=self.W - 30,
                                           height=min(700, avail), scrollbar_button_color=BORDER2)
        self.body.pack(fill="both", expand=True, padx=(8, 4), pady=(0, 14))
        self._build_setup()
        self._build_suffixes()
        self._build_work()
        self.frame.bind("<Escape>", lambda e: self.close())
        self.show("work" if self.app.yt_job else "setup")
        self.place()

    # ----- layout helpers -----
    def section(self, parent, text, top=14):
        lbl = ctk.CTkLabel(parent, text=text, font=font(11), text_color=MUTED, height=18, anchor="w")
        lbl.pack(fill="x", pady=(top, 6))
        return lbl

    def place(self):
        r = self.root
        r.update_idletasks()
        bx = self.anchor.winfo_rootx() - r.winfo_rootx()
        x = min(max(12, bx - 120), r.winfo_width() - self.W - 12)
        y = self.anchor.winfo_rooty() - r.winfo_rooty() + self.anchor.winfo_height() + 8
        self.frame.place(x=x, y=y)
        self.frame.lift()

    def is_open(self):
        return bool(self.frame.winfo_exists() and self.frame.winfo_ismapped())

    def close(self):
        self.save()
        self.frame.place_forget()

    def show(self, which):
        for name, f in (("setup", self.setup), ("suffixes", self.suf), ("work", self.work)):
            if name == which:
                f.pack(fill="x", padx=12)
            else:
                f.pack_forget()
        self.title.configure(text={"setup": "Add from YouTube", "suffixes": "File name suffixes",
                                   "work": "Add from YouTube"}[which])
        if which == "work":
            self.refresh_work()
        elif which == "setup":
            self.refresh_setup()
        self.scroll_top()

    def scroll_top(self):
        """Views have different heights; always start at the top so nothing is out of sight."""
        try:
            self.root.update_idletasks()
            self.body._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    # ----- main setup view -----
    def _build_setup(self):
        p = self.setup = ctk.CTkFrame(self.body, fg_color="transparent")
        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        self.url_var = tk.StringVar()
        self.url = ctk.CTkEntry(row, textvariable=self.url_var, placeholder_text="Paste a YouTube link",
                                height=40, font=font(12, mono=True), fg_color=FIELD, border_color=BORDER2,
                                text_color=TEXT)
        self.url.pack(side="left", fill="x", expand=True)
        ToolButton(row, "Paste", self.paste, height=40, width=70).pack(side="left", padx=(8, 0))
        self.url_var.trace_add("write", lambda *a: self._url_changed())

        card = ctk.CTkFrame(p, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=10)
        card.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(card, text="", image=icon("youtube", DIM, 30), width=56, height=44,
                     fg_color=THUMB, corner_radius=6).pack(side="left", padx=10, pady=10)
        txt = ctk.CTkFrame(card, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.info_title = ctk.CTkLabel(txt, text="", font=font(13, "bold"), text_color=TEXT, anchor="w",
                                       height=20)
        self.info_title.pack(fill="x")
        self.info_sub = ctk.CTkLabel(txt, text="", font=font(11, mono=True), text_color=MUTED, anchor="w",
                                     height=18, wraplength=330, justify="left")
        self.info_sub.pack(fill="x")

        self.section(p, "FILE NAME")
        self.name_var = tk.StringVar()
        self.name_entry = ctk.CTkEntry(p, textvariable=self.name_var, placeholder_text="Blank = video title",
                                       height=40, font=font(13), fg_color=FIELD, border_color=BORDER2,
                                       text_color=TEXT)
        self.name_entry.pack(fill="x")
        self.name_var.trace_add("write", lambda *a: self.refresh_preview())

        self.section(p, "ALSO MAKE")
        tiles = ctk.CTkFrame(p, fg_color="transparent")
        tiles.pack(fill="x")
        for i in range(3):
            tiles.grid_columnconfigure(i, weight=1, uniform="tile")
        orig = ctk.CTkFrame(tiles, fg_color="transparent", border_color=CONTROL2, border_width=1,
                            corner_radius=8, height=56)
        orig.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(orig, text=" Original", image=icon("check", GREEN, 12), compound="left",
                     font=font(13, "bold"), text_color=SOFT, anchor="w", height=20).pack(fill="x", padx=10,
                                                                                        pady=(8, 0))
        ctk.CTkLabel(orig, text="always saved", font=font(11), text_color=DIM, anchor="w", height=16).pack(
            fill="x", padx=10, pady=(0, 8))
        self.tiles = {}
        for col, key, title in ((1, "karaoke", "Karaoke"), (2, "stems", "6 stems")):
            b = ctk.CTkButton(tiles, text="", height=56, corner_radius=8, border_width=1, anchor="w",
                              compound="left", font=font(13, "bold"),
                              command=lambda k=key: self.toggle(k))
            b.grid(row=0, column=col, sticky="nsew", padx=(0, 6))
            self.tiles[key] = (b, title)
        self.cog = ctk.CTkButton(tiles, text="", image=icon("cog", SOFT, 18), width=40, height=56,
                                 corner_radius=8, fg_color=BTN, hover_color=BTN_HOVER, border_width=1,
                                 border_color=BORDER2, command=lambda: self.show("suffixes"))
        self.cog.grid(row=0, column=3, sticky="ns")
        # karaoke + stems: the karaoke file is saved but only the stems go into the workspace
        self.kar_note = ctk.CTkLabel(p, text="Karaoke-version saves to folder but is not added to workspace.",
                                     font=ctk.CTkFont(family=theme.UI, size=12, slant="italic"), text_color=MUTED,
                                     anchor="center", justify="center", wraplength=400)
        self.kar_anchor = tiles

        self.tune_box = ctk.CTkFrame(p, corner_radius=10, border_width=1)
        self.tune_box.pack(fill="x", pady=(10, 0))
        top = ctk.CTkFrame(self.tune_box, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))
        self.tune_var = tk.BooleanVar(value=self.s["tune"])
        ctk.CTkCheckBox(top, text="Tune to A = 440 Hz", variable=self.tune_var, command=self.on_tune,
                        font=font(13, "bold"), text_color=TEXT, checkbox_width=18, checkbox_height=18,
                        corner_radius=4, border_width=2, fg_color=GREEN, hover_color=GREEN,
                        border_color=CONTROL, checkmark_color=ACCENT_TXT).pack(side="left")
        ctk.CTkLabel(top, text=" BETA ", font=font(9, "bold"), text_color=AMBER, fg_color=AMBER_BADGE,
                     corner_radius=4, height=18).pack(side="left", padx=8)
        ctk.CTkLabel(self.tune_box, text="Karaoke and stems are saved in tune. The original stays untouched.",
                     font=font(12), text_color=MUTED, anchor="w", height=18, wraplength=330,
                     justify="left").pack(fill="x", padx=(40, 12), pady=(2, 10))
        self.tuned_var = tk.BooleanVar(value=self.s["tuned_original"])
        self.tuned_chk = ctk.CTkCheckBox(self.tune_box, text="Also save a tuned copy of the original",
                                         variable=self.tuned_var, command=self.on_tune, font=font(12),
                                         text_color=TEXT2, checkbox_width=16, checkbox_height=16,
                                         corner_radius=4, border_width=2, fg_color=GREEN, hover_color=GREEN,
                                         border_color=CONTROL, checkmark_color=ACCENT_TXT)

        prev = ctk.CTkFrame(p, fg_color=FIELD, border_color=BORDER, border_width=1, corner_radius=10)
        prev.pack(fill="x", pady=(12, 0))
        self.preview = ctk.CTkLabel(prev, text="", font=font(11, mono=True), text_color=SOFT, justify="left",
                                    anchor="w")
        self.preview.pack(fill="x", padx=12, pady=8)
        loc = ctk.CTkFrame(p, fg_color="transparent")
        loc.pack(fill="x", pady=(8, 0))
        self.loc_lbl = ctk.CTkLabel(loc, text="", font=font(12), text_color=MUTED, anchor="w")
        self.loc_lbl.pack(side="left", fill="x", expand=True)
        ToolButton(loc, "Change…", self.change_folder, height=28, width=80).pack(side="right")

        ctk.CTkFrame(p, fg_color=SEPARATOR, height=1, corner_radius=0).pack(fill="x", pady=(14, 12))
        foot = ctk.CTkFrame(p, fg_color="transparent")
        foot.pack(fill="x", pady=(0, 4))
        self.ws_var = tk.BooleanVar(value=self.s["workspace"])
        ctk.CTkSwitch(foot, text="Add to workspace", variable=self.ws_var, font=font(13), text_color=TEXT2,
                      progress_color=ACCENT, button_color=SWITCH_KNOB, button_hover_color=SWITCH_KNOB,
                      fg_color=SWITCH_OFF, switch_width=36, switch_height=20,
                      command=self.save).pack(side="left")
        self.go = ToolButton(foot, "Download", self.start, primary=True, height=40, width=110)
        self.go.pack(side="right")
        ToolButton(foot, "Cancel", self.close, height=40, width=84).pack(side="right", padx=8)

    def refresh_setup(self):
        for key, (b, title) in self.tiles.items():
            on = self.s[key]
            note = self.s['suffixes']['karaoke'] if key == "karaoke" else "own folder"
            b.configure(text=f" {title}\n {note}", image=icon("box_on" if on else "box_off",
                                                              ACCENT if on else CONTROL, 14),
                        fg_color=ACCENT_TINT if on else PANEL, hover_color=ACCENT_TINT_HOVER if on else BTN_HOVER,
                        border_color=ACCENT if on else BORDER2, text_color=TEXT if on else SOFT)
        if self.s["karaoke"] and self.s["stems"]:
            self.kar_note.pack(fill="x", pady=(8, 0), after=self.kar_anchor)
        else:
            self.kar_note.pack_forget()
        tune = self.tune_var.get()
        self.tune_box.configure(fg_color=GREEN_BG if tune else PANEL,
                                border_color=GREEN_BORDER if tune else BORDER2)
        if tune:
            self.tuned_chk.pack(anchor="w", padx=(40, 12), pady=(0, 10))
        else:
            self.tuned_chk.pack_forget()
        self.loc_lbl.configure(text="in " + self._short(self.s["out_root"]))
        self.refresh_preview()

    def opts(self):
        o = dict(self.s)
        o["tune"] = self.tune_var.get()
        o["tuned_original"] = self.tuned_var.get()
        o["workspace"] = self.ws_var.get()
        return o

    def current_name(self):
        n = self.name_var.get().strip()
        if n:
            return splitter.sanitize(n)
        if self.info and not self.info.get("error"):
            return splitter.sanitize(self.info["title"])
        return "[Video title]"

    def refresh_preview(self):
        name = self.current_name()
        ext = (self.info or {}).get("ext") or ".opus"
        items = splitter.plan(name, self.opts(), ext)
        notes = {"original": "original", "tuned": "tuned copy", "karaoke": "karaoke"}
        prel = splitter.project_rel(name, self.opts())
        if prel:     # the project sits in the song folder, above the stems folder
            first_sub = next((i for i, (_, r, _) in enumerate(items) if "/" in r), len(items))
            items = items[:first_sub] + [("project", prel, "")] + items[first_sub:]
            notes["project"] = "project"
        lines = [f"{name}\\"]
        width = max((len(r) for _, r, _ in items if "/" not in r), default=0) + 3
        folder_shown = False
        for key, rel, _ in items:
            if "/" in rel:
                sub, fn = rel.split("/", 1)
                if not folder_shown:
                    lines.append(f"   {sub}\\")
                    folder_shown = True
                lines.append(f"      {fn}" + ("   project" if key == "project" else ""))
            else:
                note = notes.get(key, "")
                lines.append(f"   {rel.ljust(width)}{note}".rstrip())
        self.preview.configure(text="\n".join(lines))

    @staticmethod
    def _short(path, n=44):
        path = str(path)
        return path if len(path) <= n else "…" + path[-(n - 1):]

    def toggle(self, key):
        self.s[key] = not self.s[key]
        self.save()
        self.refresh_setup()

    def on_tune(self):
        self.save()
        self.refresh_setup()

    def change_folder(self):
        d = filedialog.askdirectory(parent=self.root, initialdir=self.s["out_root"], title="Save downloads in")
        if d:
            self.s["out_root"] = d
            self.save()
            self.refresh_setup()

    def paste(self):
        try:
            self.url_var.set(self.root.clipboard_get().strip())
        except Exception:
            pass

    def save(self):
        self.s.update(self.opts())
        splitter.save_settings(self.s)

    # ----- video info -----
    def _url_changed(self):
        if self._info_job:
            self.root.after_cancel(self._info_job)
        self._info_job = self.root.after(500, self.lookup)

    def lookup(self):
        self._info_job = None
        src = self.url_var.get().strip().strip('"')
        self.info_gen += 1
        gen = self.info_gen
        if not src:
            self.info = None
            self.show_info()
            return
        if os.path.isfile(src):
            self.info = {"title": Path(src).stem, "duration": None, "ext": Path(src).suffix.lower(),
                         "quality": "local file"}
            self.show_info()
            return
        if not splitter.is_url(src):
            self.info = {"error": "That doesn't look like a link."}
            self.show_info()
            return
        self.info = {"loading": True}
        self.show_info()

        def work():
            try:
                info = splitter.fetch_info(src)
            except Exception as e:
                msg = str(e).strip().splitlines()[-1] if str(e).strip() else "Couldn't read that link."
                info = {"error": msg.replace("ERROR: ", ""), "url": src}
            self.app.events.put(("yt_info", self, gen, info))

        threading.Thread(target=work, daemon=True).start()

    def got_info(self, gen, info):
        if gen == self.info_gen:
            self.info = info
            self.show_info()

    def show_info(self):
        i = self.info
        if not i:
            self.info_title.configure(text="Paste a link to a song")
            self.info_sub.configure(text="The best audio is saved as-is; karaoke and stems are optional.",
                                    text_color=MUTED)
        elif i.get("loading"):
            self.info_title.configure(text="Looking up the video…")
            self.info_sub.configure(text="", text_color=MUTED)
        elif i.get("error"):
            self.info_title.configure(text="Can't use this link")
            self.info_sub.configure(text=i["error"][:160], text_color=AMBER_TXT)
        else:
            self.info_title.configure(text=i["title"][:60])
            q = i.get("quality") or ""
            bits = [fmt_dur(i.get("duration")), q if q == "local file" else ("best quality: " + q if q else "")]
            self.info_sub.configure(text=" · ".join(b for b in bits if b), text_color=MUTED)
            self.name_entry.configure(placeholder_text=f"Blank = {i['title'][:40]}")
        self.refresh_preview()

    # ----- suffix settings (cogwheel) -----
    def _build_suffixes(self):
        p = self.suf = ctk.CTkFrame(self.body, fg_color="transparent")
        ctk.CTkLabel(p, text="Added after the file name. The original never gets a suffix.",
                     font=font(13), text_color=MUTED, anchor="w", wraplength=420, justify="left").pack(
            fill="x", pady=(4, 10))
        grid = ctk.CTkFrame(p, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((1, 3), weight=1)
        self.suf_vars = {}
        keys = ["karaoke", "vocals", "drums", "bass", "guitar", "piano", "other", "tune"]
        for i, k in enumerate(keys):
            r, c = i // 2, (i % 2) * 2
            ctk.CTkLabel(grid, text=splitter.LABELS[k], font=font(12), text_color=TEXT2, width=70,
                         anchor="w").grid(row=r, column=c, sticky="w", padx=(0, 6), pady=4)
            v = tk.StringVar(value=self.s["suffixes"][k])
            ctk.CTkEntry(grid, textvariable=v, height=32, font=font(12, mono=True), fg_color=FIELD,
                         border_color=BORDER2, text_color=TEXT).grid(row=r, column=c + 1, sticky="ew",
                                                                     padx=(0, 12 if c == 0 else 0), pady=4)
            self.suf_vars[k] = v
        self.section(p, "STEMS FOLDER")
        self.folder_var = tk.StringVar(value=self.s["stems_folder"])
        ctk.CTkEntry(p, textvariable=self.folder_var, height=34, font=font(12, mono=True), fg_color=FIELD,
                     border_color=BORDER2, text_color=TEXT).pack(fill="x")
        self.section(p, "FORMAT FOR KARAOKE, STEMS & TUNED COPIES")
        self.fmt = ctk.CTkSegmentedButton(p, values=["FLAC", "WAV", "MP3 320", "Opus 256"], height=36,
                                          font=font(13), selected_color=ACCENT_SEL,
                                          selected_hover_color=ACCENT_SEL_HOVER, unselected_color=BTN,
                                          unselected_hover_color=BTN_HOVER, text_color=TEXT)
        self.fmt.pack(fill="x")
        ctk.CTkLabel(p, text="FLAC is lossless and about half the size of WAV – the best default.",
                     font=font(11), text_color=DIM, anchor="w").pack(fill="x", pady=(6, 0))
        btns = ctk.CTkFrame(p, fg_color="transparent")
        btns.pack(fill="x", pady=(16, 4))
        ToolButton(btns, "Reset to defaults", self.reset_suffixes, height=36).pack(side="left")
        ToolButton(btns, "Done", self.suffixes_done, primary=True, height=36, width=80).pack(side="right")
        self._load_suffix_fields()

    def _load_suffix_fields(self):
        for k, v in self.suf_vars.items():
            v.set(self.s["suffixes"][k])
        self.folder_var.set(self.s["stems_folder"])
        self.fmt.set({"MP3": "MP3 320", "OPUS": "Opus 256"}.get(self.s["fmt"], self.s["fmt"]))

    def reset_suffixes(self):
        d = splitter.default_settings()
        self.s["suffixes"], self.s["stems_folder"], self.s["fmt"] = d["suffixes"], d["stems_folder"], d["fmt"]
        self._load_suffix_fields()

    def suffixes_done(self):
        for k, v in self.suf_vars.items():
            self.s["suffixes"][k] = v.get()
        self.s["stems_folder"] = self.folder_var.get().strip() or "{name} stems"
        self.s["fmt"] = {"MP3 320": "MP3", "Opus 256": "OPUS"}.get(self.fmt.get(), self.fmt.get())
        self.save()
        self.show("setup")

    # ----- progress view -----
    def _build_work(self):
        p = self.work = ctk.CTkFrame(self.body, fg_color="transparent")
        self.work_name = ctk.CTkLabel(p, text="", font=font(13), text_color=MUTED, anchor="w")
        self.work_name.pack(fill="x", pady=(4, 8))
        self.step_rows = {}
        for k in ("download", "split", "tune", "save", "load"):
            f = ctk.CTkFrame(p, fg_color="transparent")
            row = ctk.CTkFrame(f, fg_color="transparent")
            row.pack(fill="x")
            dot = ctk.CTkLabel(row, text="", width=22, image=icon("dot", CONTROL2, 12))
            dot.pack(side="left")
            lbl = ctk.CTkLabel(row, text=STEP_TEXT[k], font=font(13), anchor="w")
            lbl.pack(side="left", padx=(6, 0))
            meta = ctk.CTkLabel(row, text="", font=font(11, mono=True), text_color=MUTED)
            meta.pack(side="right")
            bar = ctk.CTkProgressBar(f, height=6, progress_color=ACCENT, fg_color=BORDER2)
            self.step_rows[k] = (f, dot, lbl, meta, bar)
        self.work_msg = ctk.CTkLabel(p, text="", font=font(12), text_color=MUTED, anchor="w", justify="left",
                                     wraplength=420)
        self.work_msg.pack(fill="x", pady=(10, 0))
        foot = ctk.CTkFrame(p, fg_color="transparent")
        foot.pack(fill="x", pady=(12, 4))
        self.work_btn = ToolButton(foot, "Cancel", self.cancel_or_back, height=36, width=90)
        self.work_btn.pack(side="right")
        self.show_btn = ToolButton(foot, "Show folder", self.show_folder, height=36)
        self.again_btn = ToolButton(foot, "Add another", self.add_another, height=36, primary=True)

    def refresh_work(self):
        job = self.app.yt_job
        if not job:
            return
        self.work_name.configure(text=job.result["name"] if job.result else (job.name or self.current_name()))
        for k, (f, dot, lbl, meta, bar) in self.step_rows.items():
            f.pack_forget()
        for k in job.steps:
            f, dot, lbl, meta, bar = self.step_rows[k]
            f.pack(fill="x", pady=4, before=self.work_msg)
            prog = job.progress.get(k, 0.0)
            if k == "split" and job.opts["stems"]:
                lbl.configure(text="Split into stems" + (" + karaoke" if job.opts["karaoke"] else ""))
            elif k == "split":
                lbl.configure(text="Make the karaoke version")
            started = k in job.progress
            done = prog >= 1.0 or (k == "load" and job.result is not None)
            active = started and not done and job.running
            if done:
                dot.configure(image=icon("check", GREEN, 14))
                lbl.configure(text_color=TEXT, font=font(13))
                meta.configure(text="")
                bar.pack_forget()
            elif active:
                dot.configure(image=icon("dot", ACCENT, 12))
                lbl.configure(text_color=TEXT, font=font(13, "bold"))
                meta.configure(text=f"{int(prog * 100)}%" if prog > 0 else "starting…")
                bar.set(prog)
                bar.pack(fill="x", padx=(28, 0), pady=(4, 0))
            else:
                dot.configure(image=icon("dot", CONTROL2, 12))
                lbl.configure(text_color=DIM, font=font(13))
                meta.configure(text="")
                bar.pack_forget()
        self.show_btn.pack_forget()
        self.again_btn.pack_forget()
        if job.running:
            self.work_msg.configure(text="You can keep using the player meanwhile. The first split also "
                                         "downloads the AI model once.", text_color=MUTED)
            self.work_btn.configure(text="Cancel")
        elif job.error:
            self.work_msg.configure(text=job.error, text_color=AMBER_TXT)
            self.work_btn.configure(text="Back")
        else:
            res = job.result
            n = len(res["files"])
            msg = f"Saved {n} file{'s' if n > 1 else ''} in {self._short(res['folder'], 50)}"
            if res.get("tuning"):
                msg += "\n" + res["tuning"]
            self.work_msg.configure(text=msg, text_color=GREEN_TXT)
            self.work_btn.configure(text="Close")
            self.again_btn.pack(side="right", padx=8)
            self.show_btn.pack(side="left")

    def cancel_or_back(self):
        job = self.app.yt_job
        if job and job.running:
            job.cancelled = True
            self.work_msg.configure(text="Cancelling…")
            return
        if job and job.error:
            self.app.yt_job = None
            self.show("setup")
            return
        self.app.yt_job = None
        self.close()

    def add_another(self):
        self.app.yt_job = None
        self.url_var.set("")
        self.name_var.set("")
        self.show("setup")

    def show_folder(self):
        job = self.app.yt_job
        if not job or not job.result:
            return
        target = job.result["files"]["original"]
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(Path(target).parent)])
        except Exception:
            traceback.print_exc()

    # ----- start -----
    def start(self):
        src = self.url_var.get().strip().strip('"')
        if not src or not (splitter.is_url(src) or os.path.isfile(src)):
            self.info = {"error": "Paste a YouTube link first."}
            self.show_info()
            return
        if self.app.yt_job and self.app.yt_job.running:
            return
        self.save()
        name = self.name_var.get().strip()
        if not name and self.info and self.info.get("title"):
            name = self.info["title"]
        self.app.yt_job = YouTubeJob(self.app, src, name, self.opts())
        self.show("work")
