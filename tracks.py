"""Tracks in the main window: adding files, lanes, selection, reordering, track height, volume automation and the ruler."""
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

import engine
import project
import settings
from theme import *  # noqa: F401,F403
from widgets import ForkSwitch, MasterFader, ctrl_reset  # noqa: F401
from lane import Lane, VolumePopover  # noqa: F401


class TracksMixin:
    """Track handling (part of App)."""

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
        paths = self.root.tk.splitlist(event.data)
        pop = self.yt_pop
        if pop is not None and pop.is_open() and pop.accepts_drop(paths):
            return event.action        # the Split dialog takes the file to split
        self.open_paths(paths)
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
