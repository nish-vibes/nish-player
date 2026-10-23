"""GUI smoke test, used by the GitHub build:  NiSHPlayer.exe --gui-smoketest <folder>

Makes a small test song, loads it, clicks through every control, exports, and writes
gui_smoketest.txt (plus screenshots) to <folder>. Exit code 0 = passed.
"""
import os
import sys
import time
import traceback
from pathlib import Path

import numpy as np

import engine
from theme import cents_text, AMBER_BORDER


def make_song(folder, seconds=8.0, a_hz=436.8):
    """Three 'stems' of a little song tuned to A = 436.8 Hz (about 13 cents flat)."""
    sr = engine.SR
    t = np.arange(int(seconds * sr)) / sr
    note = lambda s: a_hz * 2 ** (s / 12)
    chord = sum(np.sin(2 * np.pi * note(s) * t) for s in (-9, -5, -2, 0)) * 0.15
    mel = np.zeros_like(t)
    for i, s in enumerate([0, 2, 3, 5, 7, 5, 3, 2]):
        seg = (t >= i * seconds / 8) & (t < (i + 1) * seconds / 8)
        mel[seg] = 0.35 * np.sin(2 * np.pi * note(s + 12) * t[seg])
    drums = np.random.default_rng(1).standard_normal(len(t)) * 0.4 * (np.mod(t, 0.5) < 0.06)
    paths = []
    Path(folder).mkdir(parents=True, exist_ok=True)
    for name, sig in (("My Song_VOX.wav", mel), ("My Song_DRM.wav", drums), ("My Song_OTH.wav", chord)):
        p = Path(folder) / name
        engine._encode(np.stack([sig, sig], 1).astype(np.float32), p, "WAV")
        paths.append(p)
    return paths


def run(app, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    import project
    import settings
    import updater
    settings.FILE = out / "settings.json"     # don't touch the real user settings
    app.ask_save_changes = lambda: False       # never block on a real "Save changes?" box
    report = out / "gui_smoketest.txt"
    lines = []

    def log(msg):
        lines.append(msg)
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def shot(name):
        try:
            from PIL import ImageGrab
            r = app.root
            r.update()
            x, y = r.winfo_rootx(), r.winfo_rooty()
            img = ImageGrab.grab(bbox=(x, y, x + r.winfo_width(), y + r.winfo_height()), all_screens=True)
            img.save(out / f"{name}.png")
        except Exception as e:
            log(f"(screenshot {name} skipped: {e})")

    def steps():
        root = app.root
        log(f"window up, drag-and-drop: {app.dnd}, audio device: "
            f"{'yes' if app.player.stream else 'none (' + str(app.player.device_error) + ')'}")
        shot("0-empty")
        files = make_song(out / "song")
        for f in files:  # forget names from an earlier run
            engine.save_label(f, engine.guess_label(f))
        app.add_files(files)
        t0 = time.time()
        while len(app.lanes) < 3:
            assert time.time() - t0 < 60, "files did not load"
            yield 0.1
        labels = sorted(l.track.label for l in app.lanes)
        assert labels == ["Drums", "Other", "Vocals"], labels
        assert app.song_lbl.cget("text") == "My Song", app.song_lbl.cget("text")
        log(f"ok: loaded 3 tracks {labels}, song name 'My Song'")
        app.add_files(files)  # duplicates are ignored
        yield 0.3
        assert len(app.lanes) == 3
        log("ok: duplicate files ignored")

        # rename (file name stays the same)
        lane = next(l for l in app.lanes if l.track.label == "Vocals")
        lane.name.focus_set()
        lane.name_var.set("Lead vocals")
        root.focus_set()
        lane._commit_name()
        yield 0.2
        assert lane.track.label == "Lead vocals" and Path(lane.track.path).name == "My Song_VOX.wav"
        assert engine.load_labels().get(str(Path(lane.track.path).resolve())) == "Lead vocals"
        log("ok: renamed track, label remembered, file untouched")

        # mute / solo / volume
        drums = next(l for l in app.lanes if l.track.label == "Drums")
        drums.mute_btn.invoke()
        lane.solo_btn.invoke()
        g = dict(zip([l.track.label for l in app.lanes], app.player.gains()))
        assert g == {"Lead vocals": 1.0, "Drums": 0.0, "Other": 0.0}, g
        assert drums.silent
        lane.solo_btn.invoke()
        lane.vol.set(60)
        lane.on_volume(60)
        g = dict(zip([l.track.label for l in app.lanes], app.player.gains()))
        assert g == {"Lead vocals": 0.6, "Drums": 0.0, "Other": 1.0}, g
        log("ok: mute, solo and volume")

        # selection, keyboard S / M, Ctrl+click on S, reorder with the grip
        assert app.selected is app.lanes[0] and app.lanes[0].selected
        Lane = type(app.lanes[0])
        other = app.lanes[2]
        other.canvas.event_generate("<Button-1>", x=40, y=30)
        yield 0.2
        assert app.selected is other and other.selected and not app.lanes[0].selected
        app.root.focus_force()
        yield 0.2
        before = (other.track.solo, other.track.mute)
        app.root.event_generate("<KeyPress-s>", keysym="s")
        app.root.event_generate("<KeyPress-m>", keysym="m")
        yield 0.2
        if (other.track.solo, other.track.mute) == before:   # no keyboard focus on this display
            app._selected_key(Lane.toggle_solo)
            app._selected_key(Lane.toggle_mute)
        assert other.track.solo != before[0] and other.track.mute != before[1]
        app._selected_key(Lane.toggle_solo)
        app._selected_key(Lane.toggle_mute)
        assert (other.track.solo, other.track.mute) == before
        log("ok: click selects a track; S and M toggle solo and mute on it")
        for l in app.lanes:
            l.track.solo = True
        app.refresh_lanes()
        target = app.lanes[1]
        target.solo_btn._canvas.event_generate("<Control-Button-1>", x=6, y=6, state=0x0004)
        yield 0.2
        assert [l.track.solo for l in app.lanes] == [False, True, False], [l.track.solo for l in app.lanes]
        app._selected_key(app.solo_only)   # solo-only again on the only soloed track turns it off
        assert not any(l.track.solo for l in app.lanes)
        log("ok: Ctrl+click on S solos only that track (again = off)")
        first = app.lanes[0]

        class E:
            pass
        ev = E()
        app.drag_start(first, ev)
        last = app.lanes[-1]
        ev.y_root = last.frame.winfo_rooty() + last.frame.winfo_height() - 5
        app.drag_move(first, ev)
        app.drag_end(first, ev)
        yield 0.3
        assert app.lanes[-1] is first and app.player.tracks[-1] is first.track
        assert first.frame.winfo_y() > app.lanes[0].frame.winfo_y()
        app.move_lane(first, 0)
        yield 0.2
        assert app.lanes[0] is first and app.player.tracks[0] is first.track
        log("ok: drag the six-dot grip to reorder tracks (player order follows)")

        # seek
        app.seek(0.5)
        yield 0.1
        assert abs(app.player.position() - 0.5) < 0.01
        assert lane.played == len(lane.bars) // 2 or abs(lane.played - len(lane.bars) / 2) <= 1
        log(f"ok: seek, waveform bars={len(lane.bars)}")

        # speed and pitch (live)
        app.speed_slider.set(0.85)
        app.on_speed(0.85)
        app.pitch_slider.set(-2)
        app.on_pitch(-2)
        assert app.player.key() == (0.85, -2.0, False), app.player.key()  # heard at once (live)
        app.player.playing = True
        app.player.render_block(1024)
        assert app.player.mode == "live"
        app.player.playing = False
        log("ok: slider change goes to the real-time stretcher immediately")
        yield 0.6
        assert app.busy_lbl.cget("text").strip() == "Polishing…" and app.busy_lbl.cget("image"), \
            app.busy_lbl.cget("text")
        log("ok: spinner + 'Polishing…' while the high-quality version renders")
        t0 = time.time()
        while app.player.render_busy:
            assert time.time() - t0 < 90
            yield 0.2
        yield 0.2
        assert app.busy_lbl.cget("text").startswith("Tip") and not app.busy_lbl._label.cget("image"), \
            "spinner should disappear when done"
        yield 0.5
        t0 = time.time()
        while app.player.render_busy or any(t.buf_key != (0.85, -2.0, False) for t in app.player.tracks):
            assert time.time() - t0 < 90, "speed/pitch render timed out"
            yield 0.2
        n0 = app.player.source_length()
        assert abs(app.player.length() / n0 - 1 / 0.85) < 0.02
        assert abs(app.player.position() - 0.5) < 0.02
        assert app.speed_val.cget("text") == "0.85×" and app.pitch_val.cget("text") == "−2 semitones"
        log(f"ok: live speed 0.85x / pitch -2 st in {time.time() - t0:.1f}s, playhead kept")

        # manual fine tune, then Auto 440 overrides it
        app.fine_slider.set(12)
        app.on_fine(12)
        assert app.fine_val.cget("text") == "+12 ct"
        app.auto_chk.toggle()                      # the Auto 440 switch
        assert app.auto and app.auto_var.get()
        t0 = time.time()
        while app.analysing:
            assert time.time() - t0 < 60, "Auto 440 analysis timed out"
            yield 0.2
        yield 0.5
        corr, a_hz, conf = app.auto_result
        assert 9 <= corr <= 16 and abs(a_hz - 436.8) < 1.5, app.auto_result
        assert app.fine_slider.cget("state") == "disabled"
        assert abs(app.fine_slider.get() - corr) <= 1
        assert app.fine_val.cget("text") == cents_text(corr), app.fine_val.cget("text")
        log(f"ok: Auto 440 detected A = {a_hz:.1f} Hz -> {corr:+.1f} ct, slider locked at "
            f"{app.fine_val.cget('text')}")
        t0 = time.time()
        want = (round(app.speed, 6), -2.0, round(app.current_cents(), 6))   # Rubber Band, then varispeed
        while app.player.render_busy or any(t.buf_key != want for t in app.player.tracks):
            assert time.time() - t0 < 90, "Auto 440 render timed out"
            yield 0.2
        log("ok: Auto 440 correction applied to playback")

        # master fader and clip light (latches until clicked)
        app.fader.set_pos(0.7)
        assert abs(app.player.master - 10 ** (-3 / 20)) < 0.01, app.player.master
        app.fader.set_pos(0.8)
        app.player.clip = True
        yield 0.2
        assert app.fader.clip_shown
        app.player.process_master(np.zeros((64, 2), np.float32))
        yield 0.2
        assert app.fader.clip_shown, "clip light should stay on"
        app.fader.clip_btn.invoke()
        yield 0.2
        assert not app.fader.clip_shown and not app.player.clip
        log("ok: master fader, clip light latches and resets on click")

        # playback (only if this machine has an audio device)
        if app.player.stream is not None:
            app.seek(0)
            app.toggle_play()
            yield 1.0
            moved = app.player.position()
            app.toggle_play()
            assert moved > 0, "playhead did not move"
            log(f"ok: played 1 s (position {moved:.3f})")
        else:
            log("skip: no audio device on this machine, playback not tested")
        app.seek(0.33)
        yield 0.3
        shot("1-loaded")

        # export dialog
        app.open_export()
        yield 0.8
        d = app.export_dialog
        assert d is not None
        assert d.tags == ["0.85x", "-2semitones", "440hz"], d.tags
        assert d.name_var.get() == "My Song_mix_0.85x_-2semitones_440hz", d.name_var.get()
        try:
            from PIL import ImageGrab
            w = d.win
            w.update()
            x, y = w.winfo_rootx(), w.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x + w.winfo_width(), y + w.winfo_height()),
                           all_screens=True).save(out / "2-export.png")
        except Exception as e:
            log(f"(export screenshot skipped: {e})")
        d.folder = str(out / "export")
        d.fmt.set("MP3 320")
        d.refresh()
        d.start()
        t0 = time.time()
        while d.busy:
            assert time.time() - t0 < 120, "export timed out"
            yield 0.2
        assert d.written, d.msg.cget("text")
        mp3 = Path(d.written[0])
        secs = engine.probe_seconds(mp3)
        assert mp3.name == "My Song_mix_0.85x_-2semitones_440hz.mp3" and abs(secs - 8 / 0.85) < 0.2, (mp3, secs)
        log(f"ok: exported mix {mp3.name} ({secs:.2f} s)")
        d.mode.set("each")
        d.fmt.set("WAV")
        d.refresh()
        d.start()
        t0 = time.time()
        while d.busy:
            assert time.time() - t0 < 120, "export timed out"
            yield 0.2
        names = sorted(Path(p).name for p in d.written)
        assert names == ["My Song_DRM_0.85x_-2semitones_440hz.wav", "My Song_OTH_0.85x_-2semitones_440hz.wav",
                         "My Song_VOX_0.85x_-2semitones_440hz.wav"], names
        log(f"ok: exported each track: {names}")
        d.close()
        yield 0.2

        # Auto 440 off -> manual value comes back
        app.auto_var.set(False)
        app.on_auto()
        yield 0.2
        assert app.fine_val.cget("text") == "+12 ct" and app.fine_slider.cget("state") == "normal"
        log("ok: Auto 440 off restores the manual fine tune")

        # Ctrl+click puts sliders back to their defaults
        def ctrl_click(slider):
            c = slider._canvas
            c.event_generate("<Control-Button-1>", x=c.winfo_width() // 4, y=c.winfo_height() // 2,
                             state=0x0004)
        for sl in (app.speed_slider, app.pitch_slider, app.fine_slider, lane.vol):
            ctrl_click(sl)
        app.fader.set_pos(0.3)
        fc = app.fader.canvas
        fc.event_generate("<Control-Button-1>", x=60, y=40, state=0x0004)
        yield 0.3
        assert app.speed == 1.0 and app.semis == 0 and app.manual_cents == 0, (app.speed, app.semis,
                                                                               app.manual_cents)
        assert lane.track.volume == 1.0 and abs(app.fader.pos - 0.8) < 1e-6
        assert app.player.key() == (1.0, 0.0, 0.0)
        log("ok: Ctrl+click resets speed, pitch, fine tune, track volume and master")

        # fine-tuning is always varispeed (pitch and tempo together, no compensation)
        for c in (3, 12, -40):
            app.fine_slider.set(c)
            app.on_fine(c)
            yield 0.2
            assert app.player.varispeed and app.player.key() == (1.0, 0.0, float(c)), app.player.key()
        app.open_export()
        yield 0.6
        d = app.export_dialog
        d.folder = str(out / "export-vari")
        d.fmt.set("WAV")
        d.mode.set("mix")
        d.refresh()
        d.start()
        while d.busy:
            yield 0.2
        sv = engine.probe_seconds(d.written[0])
        d.close()
        n_sec = app.player.source_length() / engine.SR
        assert abs(sv - n_sec / engine.vari_ratio(-40)) < 0.03, (sv, n_sec)
        log(f"ok: fine-tuning is always varispeed (live + export −40 ct: {n_sec:.3f} s → {sv:.3f} s)")

        app.fine_slider.set(0)
        app.on_fine(0)
        # Auto 440 has no dead zone: +3 ct is simply corrected
        app.auto_var.set(True)
        app.on_auto()
        yield 0.1
        app._analysis_gen += 1
        app.analysing = True
        app._style_fine()
        assert app.fine_val.cget("text") == "…"
        app.events.put(("analysed", app._analysis_gen, (3.0, 439.24, 0.95)))  # A=439.24 -> +3.0 ct
        yield 0.4
        assert app.auto and app.current_cents() == 3.0 and app.player.varispeed
        assert app.fine_val.cget("text") == "+3 ct", app.fine_val.cget("text")
        shot("4b-auto440")
        # Auto 440 can't detect the tuning: a popup, and Auto 440 turns itself off
        app._analysis_gen += 1
        app.analysing = True
        app.events.put(("analysed", app._analysis_gen, (0.0, None, 0.0)))
        yield 0.6
        assert not app.auto and not app.auto_var.get() and app.auto_result is None
        w = app.alert_win
        assert w is not None and w.winfo_exists() and w.title() == "Auto 440"
        shot("4c-alert")
        try:
            from PIL import ImageGrab
            w.update()
            ImageGrab.grab(bbox=(w.winfo_rootx(), w.winfo_rooty(), w.winfo_rootx() + w.winfo_width(),
                                 w.winfo_rooty() + w.winfo_height())).save(out / "4d-alert-box.png")
        except Exception:
            pass
        w.destroy()
        yield 0.2
        log("ok: Auto 440 corrects small offsets too (no dead zone); 'couldn't detect' popup turns it off")

        # projects: save, change something, reopen -> everything comes back
        from tkinter import filedialog as fd
        real_ask = fd.asksaveasfilename
        fd.asksaveasfilename = lambda **kw: str(out / "Test Project.nish")
        lane0 = app.lanes[0]
        lane0.vol.set(55)
        lane0.on_volume(55)
        for i, l in enumerate(app.lanes):
            l.track.mute, l.track.solo = (i == 1), False
        app.refresh_lanes()
        app.speed_slider.set(0.9)
        app.on_speed(0.9)
        app.player.set_region(engine.SR * 1, engine.SR * 3)
        app.refresh_region()
        n_tracks = len(app.lanes)
        names = [l.track.label for l in app.lanes]
        assert app.save_project()
        fd.asksaveasfilename = real_ask
        pth = out / "Test Project.nish"
        assert pth.exists() and app.project_path == str(pth) and not app.is_dirty()
        app._update_title()
        assert app.root.title().startswith("Test Project – "), app.root.title()
        app.speed_slider.set(1.0)
        app.on_speed(1.0)
        app._update_title()
        assert app.is_dirty() and "•" in app.root.title()
        asked = []
        app.ask_save_changes = lambda: (asked.append(1), False)[1]      # "Don't save"
        app.open_project(pth)
        for _ in range(100):
            if app.project_path and len(app.lanes) == n_tracks and not app.loading:
                break
            yield 0.1
        assert asked == [1]
        assert [l.track.label for l in app.lanes] == names
        assert abs(app.lanes[0].track.volume - 0.55) < 1e-6, [(l.track.label, l.track.volume, l.track.mute)
                                                              for l in app.lanes]
        assert app.lanes[1].track.mute, [(l.track.label, l.track.volume, l.track.mute) for l in app.lanes]
        assert app.speed == 0.9 and app.player.region == (engine.SR * 1.0, engine.SR * 3.0), app.player.region
        assert not app.is_dirty()
        app.open_recent()
        yield 0.3
        rp = app.recent_pop
        assert rp.is_open() and rp.rows and Path(rp.rows[0][0]) == pth.resolve()
        shot("7-recent")
        rp.close()
        app.ask_save_changes = lambda: False
        app.lanes[1].toggle_mute()
        assert app.is_dirty()
        app.speed_slider.set(1.0)
        app.on_speed(1.0)
        app.player.set_region(None, None)
        app.refresh_region()
        app._set_project(None)
        log("ok: project saved, '•' when changed, 'save changes?' asked, reopened with names, volume, "
            "mute, speed and loop area; listed under Open ▾")

        # .nish files open with this app (Windows build only: written for the current user, no admin)
        if sys.platform == "win32" and getattr(sys, "frozen", False):
            import instance
            import winreg
            instance.register_file_type()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Classes\NiSHPlayer.Project\shell\open\command") as k:
                cmd = winreg.QueryValueEx(k, "")[0]
            assert str(Path(sys.executable).resolve()) in cmd and '"%1"' in cmd, cmd
            log(f"ok: .nish registered for double-click: {cmd}")

        # export folder: the open project's (song) folder when there is one
        proj_path = str(pth)
        app.project_path = proj_path
        app.open_export()
        yield 0.5
        d = app.export_dialog
        assert d.folder == str(Path(proj_path).parent), d.folder
        assert "song folder" in d.loc_lbl.cget("text"), d.loc_lbl.cget("text")
        d.close()
        log("ok: exports go to the open project's folder")
        app.project_path = None
        # otherwise the Desktop by default; "Change…" makes the new folder the default
        assert settings.export_folder() == settings.desktop()
        app.open_export()
        yield 0.5
        d = app.export_dialog
        assert d.folder == settings.desktop(), d.folder
        d.close()
        settings.set_export_folder(str(out))
        app.open_export()
        yield 0.5
        assert app.export_dialog.folder == str(out)
        app.export_dialog.close()
        log(f"ok: export folder defaults to the Desktop ({settings.desktop()}) and remembers a new choice")

        # volume automation (A): flat line at the current volume, click adds, drag moves, double-click deletes
        import theme as _th
        import project as _proj
        E = lambda **k: type("E", (), {"x": 0, "y": 0, "y_root": 0, **k})()
        lane = app.lanes[0]
        lane.vol.set(80)
        lane.on_volume(80)
        lane.auto_btn.invoke()
        yield 0.3
        t = lane.track
        assert t.auto_on and len(t.auto_pts) == 2 and abs(t.auto_pts[0][1] - 0.8) < 1e-6, t.auto_pts
        assert lane.vol_lbl.cget("text") == "Auto" and lane.vol.cget("state") == "disabled"
        assert lane.auto_btn.cget("fg_color") == _th.GREEN_BG
        mid_t = t.auto_pts[-1][0] / 2
        x, y = lane._xy(mid_t, 0.8)
        lane._press(E(x=int(x), y=int(y)))
        _, y2 = lane._xy(mid_t, 0.3)
        lane._motion(E(x=int(x), y=int(y2)))
        yield 0.2
        shot("8-automation")
        lane._release(E(x=int(x), y=int(y2)))
        assert len(t.auto_pts) == 3 and abs(t.auto_pts[1][1] - 0.3) < 0.05, t.auto_pts
        assert abs(float(t.envelope(np.array([t.auto_pts[1][0] * engine.SR]))[0]) - t.auto_pts[1][1]) < 1e-3
        app.open_export()
        yield 0.5
        def texts(w):
            out = []
            for c in w.winfo_children():
                try:
                    out.append(str(c.cget("text")))
                except Exception:
                    pass
                out += texts(c)
            return out
        assert any(f"Automation: {t.label}" in x for x in texts(app.export_dialog.win)), texts(app.export_dialog.win)
        app.export_dialog.close()
        st = app.project_state()
        assert st["tracks"][0]["automation"]["on"] and len(st["tracks"][0]["automation"]["points"]) == 3
        p2 = _proj.save(out / "Automation.nish", st)
        app.ask_save_changes = lambda: False
        app.open_project(p2)
        for _ in range(100):
            if app.project_path and len(app.lanes) == n_tracks and not app.loading:
                break
            yield 0.1
        yield 0.5                      # let the waveforms draw at their real width
        lane = app.lanes[0]
        t = lane.track
        assert t.auto_on and len(t.auto_pts) == 3 and lane.vol_lbl.cget("text") == "Auto", t.auto_pts
        px, py = lane._xy(*t.auto_pts[1])
        lane._double(E(x=int(px), y=int(py)))
        assert len(t.auto_pts) == 2
        lane.auto_btn.invoke()
        assert not t.auto_on and len(t.auto_pts) == 2 and not t.automation_active()
        assert lane.vol.cget("state") == "normal" and lane.vol_lbl.cget("text") == "80%"
        app._set_project(None)
        log("ok: volume automation: A on/off, add, drag, delete, export chip, saved and reopened in a project")

        # one height for every track: drag an edge, compact mode with V/A/M/S and the volume popover
        assert app.track_h == 92 and app.lanes[0].head.cget("height") == 92
        app.resize_start(lane, E(y_root=500))
        app.resize_move(E(y_root=540))
        yield 0.2
        assert app.track_h == 132 and all(l.head.cget("height") == 132 for l in app.lanes)
        assert app._resize_hint.winfo_ismapped() and "132 px" in app._resize_hint.cget("text")
        shot("9-resize")
        app.resize_end()
        assert settings.get("track_height") == 132
        app.resize_start(lane, E(y_root=500))
        app.resize_move(E(y_root=0))
        app.resize_end()
        assert app.track_h == 44 and lane.compact, app.track_h
        app.set_track_height(132, save=True)
        app.toggle_compact()
        yield 0.3
        assert app.track_h == 44 and all(l.compact for l in app.lanes)
        assert lane.v_btn.winfo_ismapped() and not lane.volrow.winfo_ismapped()
        cols = [int(w.grid_info()["column"]) for w in (lane.v_btn, lane.auto_btn, lane.mute_btn, lane.solo_btn)]
        assert cols == sorted(cols), cols                       # V, A, M, S
        lane.v_btn.invoke()
        yield 0.3
        assert app.vol_pop and app.vol_pop.is_open() and lane.v_btn.cget("border_color") == _th.ACCENT, (
            app.vol_pop, app.vol_pop and app.vol_pop.is_open(), lane.v_btn.cget("border_color"))
        app.vol_pop.slider.set(40)
        app.vol_pop.on_change(40)
        assert abs(lane.track.volume - 0.4) < 1e-6
        shot("10-compact")
        lane.v_btn.invoke()
        assert app.vol_pop is None
        app.toggle_compact()
        yield 0.2
        assert app.track_h == 132 and not lane.compact and lane.volrow.winfo_ismapped()
        assert int(lane.auto_btn.grid_info()["column"]) == int(lane.solo_btn.grid_info()["column"])  # A under S
        app.set_track_height(engine_default := 92, save=True)
        log("ok: track height: drag an edge (all tracks follow, remembered), compact mode V/A/M/S with the "
            "volume popover, back to the previous height")

        # settings cog: manual update check (GitHub simulated), YouTube-failure notice
        assert not hasattr(app, "clear_btn")
        real_check = updater.check
        updater.check = lambda: {"tag": "v9.9.9", "newer": True, "url": "https://example.invalid/x.zip",
                                 "size": 268_000_000, "notes": ""}
        app.cog_btn.invoke()
        yield 0.4
        m = app.settings_pop
        assert m.is_open() and m.btn.cget("text") == "Check for updates" and not m.notice.winfo_ismapped()
        m.btn.invoke()
        for _ in range(30):
            if m.state != "checking":
                break
            yield 0.1
        yield 0.3
        assert m.state == "newer" and "9.9.9 is available (268 MB)" in m.msg.cget("text"), m.msg.cget("text")
        assert m.btn.cget("text") in ("Download", "Open download page"), m.btn.cget("text")
        shot("6-update")
        # after the download: a 'ready' message and a separate Close and update button
        installed = []
        real_install = app.install_update
        app.install_update = lambda stage: installed.append(stage)
        m.state, m.stage = "ready", out / "fake.new"
        m.refresh()
        yield 0.2
        assert "downloaded and ready to install" in m.msg.cget("text") and m.btn.cget("text") == "Close and update"
        shot("6a-update-ready")
        assert not installed
        m.btn.invoke()
        yield 0.2
        assert installed == [out / "fake.new"] and m.state == "installing"
        app.install_update = real_install
        updater.check = lambda: {"tag": updater.current_tag(), "newer": False, "url": None, "size": None,
                                 "notes": ""}
        m.state = "idle"
        m.btn.invoke()
        for _ in range(30):
            if m.state != "checking":
                break
            yield 0.1
        yield 0.3
        assert m.state == "latest" and "latest version" in m.msg.cget("text")
        updater.check = real_check
        for _ in range(5):
            app.note_yt_failure()
        yield 0.2
        assert m.notice.winfo_ismapped() and "failed 5 times today" in m.notice_lbl.cget("text")
        assert app.cog_btn.cget("border_color") == AMBER_BORDER
        shot("6b-update-notice")
        m.close()
        settings.put("yt_failures", {})
        app._style_cog()
        log("ok: cog menu: Check for updates -> Download -> ready -> Close and update / latest version; "
            "amber notice after 5 failed YouTube extractions today")

        # theme: dark by default, switched in the cog menu, remembered; window rebuilt in place
        import theme
        assert theme.MODE == "dark" and settings.get("theme", "dark") == "dark"
        n_lanes = len(app.lanes)
        vols = [round(l.track.volume, 3) for l in app.lanes]
        speed = app.speed
        app.open_settings()
        yield 0.3
        assert app.settings_pop.theme_btn.cget("text") == "Dark"
        app.settings_pop.theme_btn.invoke()
        yield 0.8
        assert theme.MODE == "light" and settings.get("theme") == "light"
        assert app.root.cget("fg_color") in (theme.PALETTE["BG"][1], ("gray92", "gray14")) or \
            theme.PALETTE["BG"][1] in str(app.root.cget("fg_color")), app.root.cget("fg_color")
        assert len(app.lanes) == n_lanes and [round(l.track.volume, 3) for l in app.lanes] == vols
        assert app.speed == speed and app.lanes[0].canvas.cget("bg") in (PANEL_L := theme.PALETTE["PANEL"][1],
                                                                          theme.PALETTE["SELECTED_WAVE"][1])
        assert app.settings_pop is not None and app.settings_pop.is_open()
        assert app.settings_pop.theme_btn.cget("text") == "Light"
        app.settings_pop.close()
        yield 0.3
        shot("8-light")
        app.open_export()
        yield 0.6
        shot("8b-light-export")
        app.export_dialog.close()
        app.open_youtube()
        yield 0.6
        shot("8c-light-youtube")
        app.yt_pop.close()
        app.apply_theme("dark")
        yield 0.6
        assert theme.MODE == "dark" and settings.get("theme") == "dark" and len(app.lanes) == n_lanes
        log("ok: theme switch in the cog menu: dark (default) -> light -> dark, remembered, tracks kept")

        # loop area: drag on the timeline, loop button, export only the area, clear with ×
        rc = app.ruler
        span = app._ruler_span()
        x_a, x_b = 8 + span * 0.25, 8 + span * 0.6
        rc.event_generate("<Button-1>", x=int(x_a), y=15)
        rc.event_generate("<B1-Motion>", x=int(x_a) + 30, y=15)
        rc.event_generate("<B1-Motion>", x=int(x_b), y=15)
        rc.event_generate("<ButtonRelease-1>", x=int(x_b), y=15)
        yield 0.2
        n_src = app.player.source_length()
        r = app.player.region
        assert r and abs(r[0] / n_src - 0.25) < 0.02 and abs(r[1] / n_src - 0.6) < 0.02, r
        rc.event_generate("<Button-1>", x=int(8 + span * 0.8), y=15)        # plain click = seek
        rc.event_generate("<ButtonRelease-1>", x=int(8 + span * 0.8), y=15)
        yield 0.2
        assert app.player.region == r and abs(app.player.position() - 0.8) < 0.02
        assert app.player.active_region() is None
        app.loop_btn.invoke()
        yield 0.2
        assert app.player.loop and app.player.active_region() == r
        assert app.fade_inner.winfo_ismapped() and app.player.loop_fade == 1.0
        app.fade_slider.set(0.5)
        app.on_fade(0.5)
        assert app.player.loop_fade == 0.5 and app.fade_val.cget("text") == "0.5 s"
        c = app.fade_slider._canvas
        c.event_generate("<Control-Button-1>", x=10, y=8, state=0x0004)
        yield 0.2
        assert app.player.loop_fade == 1.0, app.player.loop_fade
        log("ok: drag on the timeline marks a loop area; click still seeks; loop uses the area; "
            "Fade slider shows with loop (1 s default, Ctrl+click resets)")
        shot("5-loop")
        app.open_export()
        yield 0.8
        d = app.export_dialog
        assert d.region == r and any("m" in t and "-" in t for t in d.tags), d.tags
        d.folder = str(out / "export-loop")
        d.fmt.set("WAV")
        d.mode.set("mix")
        d.refresh()
        d.start()
        t0 = time.time()
        while d.busy:
            assert time.time() - t0 < 120
            yield 0.2
        secs = engine.probe_seconds(d.written[0])
        want = (r[1] - r[0]) / engine.SR
        assert abs(secs - want) < 0.1, (secs, want)
        log(f"ok: export with loop on writes only the area: {Path(d.written[0]).name} ({secs:.2f} s)")
        d.close()
        yield 0.2
        x1 = app._src_to_x(r[1])
        cx = x1 - 9 if x1 - app._src_to_x(r[0]) > 40 else x1 + 10
        rc.event_generate("<Button-1>", x=int(cx), y=15)
        rc.event_generate("<ButtonRelease-1>", x=int(cx), y=15)
        yield 0.2
        assert app.player.region is None
        app.loop_btn.invoke()
        yield 0.2
        assert not app.fade_inner.winfo_ismapped()
        log("ok: × clears the loop area; Fade slider hides when loop is off")

        # remove and clear
        drums = next(l for l in app.lanes if l.track.label == "Drums")   # lanes were rebuilt by the project reopen
        app.remove_lane(drums)
        yield 0.2
        assert len(app.lanes) == 2 and len(app.player.tracks) == 2
        app.clear_all()
        yield 0.2
        assert not app.lanes and app.count_lbl.cget("text") == "NO TRACKS"
        log("ok: remove track and clear all")

        # Add from YouTube – a local file stands in for the download; the AI split is real
        import splitter
        if os.environ.get("NISH_FAKE_SPLIT"):
            def fake(audio, model, on_progress, check_cancel):
                on_progress(0.5)
                names = splitter.SIX if model == "htdemucs_6s" else ["vocals", "drums", "bass", "other"]
                return {n: audio * (0.5 if n in ("vocals", "other") else 0.0) for n in names}
            splitter.SEPARATOR = fake
        mix = sum(engine.decode(f) for f in files)
        song = out / "song" / "Smoke Song source.wav"
        engine._encode(mix, song, "WAV")
        app.open_youtube()
        yield 0.5
        pop = app.yt_pop
        assert pop.is_open() and app.yt_btn.cget("text") == "Split…"
        assert pop.title.cget("text") == "Split song"
        pop.set_source("youtube")
        yield 0.2
        assert pop.yt_row.winfo_ismapped() and not pop.file_row.winfo_ismapped()
        assert pop.go.cget("text") == "DOWNLOAD" and "always kept" in pop.tiles["original"][0].cget("text")
        pop.toggle("original")                      # YouTube: the original can't be unticked
        assert splitter.effective(pop.s, False)[0]["original"]
        pop.set_source("file")                      # Split a file on this computer
        yield 0.2
        assert pop.file_row.winfo_ismapped() and not pop.yt_row.winfo_ismapped() and pop.drop_tip.winfo_ismapped()
        assert not pop.accepts_drop([str(song), str(song)])            # one file at a time
        assert pop.accepts_drop([str(song)])                           # dropped onto the window
        yield 1.0
        assert pop.file_var.get() == str(song) and pop.s["source"] == "file"
        assert pop.info and pop.info.get("title") == "Smoke Song source", pop.info
        assert pop.info.get("duration", 0) > 1 and "from this computer" in pop.info_sub.cget("text"), pop.info
        pop.name_var.set("Smoke Song")
        pop.s.update(out_root=str(out / "yt"))
        pop.s["out"] = {"original": True, "karaoke": True, "stems": True, "stems6": False}
        pop.s["tune"] = {"original": True, "karaoke": True, "stems": True}
        pop.toggle("stems6")                        # Stems ×6 replaces Stems
        assert pop.s["out"]["stems6"] and not pop.s["out"]["stems"]
        pop.ws_var.set(True)
        pop.refresh_setup()
        assert pop.go.cget("text") == "SPLIT" and "a copy" in pop.tiles["original"][0].cget("text")
        shown = [k for k, b in pop.tune_btns.items() if b.winfo_ismapped()]
        yield 0.2
        shown = [k for k, b in pop.tune_btns.items() if b.winfo_ismapped()]
        assert shown == ["original", "karaoke", "stems6"], shown          # one Auto 440 button per download
        pop.toggle_tune("karaoke")
        assert not pop.s["tune"]["karaoke"]
        pop.toggle_tune("karaoke")
        assert "Desktop" not in splitter.location(pop.s) and pop.loc_lbl.cget("text").strip().endswith("yt")
        pop.cog.invoke()
        yield 0.3
        assert pop.suf.winfo_ismapped()
        pop.suf_vars["karaoke"].set("KARAOKE")
        pop.fmt.set("FLAC")
        pop.suffixes_done()
        yield 0.3
        txt = pop.preview.cget("text")
        assert txt.splitlines()[1].strip().startswith("~Smoke Song.nish"), txt     # project at the top
        for want in ("Smoke Song Original.wav", "Smoke Song Auto440.flac", "Smoke Song KARAOKE Auto440.mp3",
                     "Separated Stems - Smoke Song", "Smoke Song VOX Auto440.flac", "Smoke Song KEYS Auto440.flac"):
            assert want in txt, (want, txt)
        log("ok: Split popover: YouTube link or a file (Browse or drop), name, karaoke + stems, Auto 440 + "
            "tuned copy, suffixes, folder preview")
        shot("3-youtube")
        pop.body._parent_canvas.yview_moveto(1.0)   # scrolled down to reach the Download button
        yield 0.2
        pop.go.invoke()
        yield 0.3
        job = app.yt_job
        assert job is not None and pop.work.winfo_ismapped()
        assert pop.body._parent_canvas.yview()[0] == 0.0, "progress view must start at the top"
        f, dot, lbl, meta, bar = pop.step_rows["download"]
        for _ in range(30):                          # give a busy machine time to lay out the rows
            if f.winfo_ismapped() and f.winfo_y() < 200:
                break
            yield 0.1
        assert f.winfo_ismapped() and f.winfo_y() < 200, "download step not visible"
        assert lbl.cget("text") == "Read the file" and pop.title.cget("text") == "Splitting…", (
            lbl.cget("text"), pop.title.cget("text"))
        log("ok: progress view shows the steps at once, scrolled to the top")
        shot("3b-youtube-working")
        pop.close()
        yield 0.4
        assert app.yt_btn.cget("text") != "Split…", app.yt_btn.cget("text")
        assert "YouTube" not in app.status.cget("text"), app.status.cget("text")
        log(f"ok: popover closed, header button spins: '{app.yt_btn.cget('text')}'")
        app.open_youtube()
        yield 0.3
        assert pop.work.winfo_ismapped()
        t0 = time.time()
        while job.running:
            assert time.time() - t0 < 1200, "YouTube job timed out"
            yield 0.5
        assert not job.error, job.error
        folder = out / "yt" / "Smoke Song"
        made = sorted(str(p.relative_to(folder)).replace("\\", "/") for p in folder.rglob("*.*"))
        log(f"ok: split took {time.time() - t0:.0f}s, wrote {made}; {job.result['tuning']}")
        if getattr(sys, "frozen", False):   # the built app: the AI models ship with it, nothing downloaded
            import splitter
            import torch
            have = splitter.bundled_models()
            assert len(have) >= 2, f"AI models missing from the app: {have}"
            if not os.environ.get("NISH_FAKE_SPLIT"):
                assert Path(torch.hub.get_dir()).resolve() == splitter.MODELS_DIR.resolve(), torch.hub.get_dir()
            log(f"ok: AI models bundled with the app: {have}")
        assert len(made) == 10 and "~Smoke Song.nish" in made and "Smoke Song KARAOKE Auto440.mp3" in made, made
        t0 = time.time()
        while len(app.lanes) < 6:
            assert time.time() - t0 < 60, "stems were not added to the workspace"
            yield 0.2
        labels = [l.track.label for l in app.lanes]
        assert labels == ["Vocals", "Drums", "Bass", "Guitar", "Piano", "Other"], labels   # no karaoke
        for _ in range(30):
            if app.project_path:
                break
            yield 0.1
        assert app.project_path and Path(app.project_path).name == "~Smoke Song.nish", app.project_path
        assert not app.is_dirty() and project.recent()[0] == str(Path(app.project_path).resolve())
        yield 0.5
        shot("4-youtube-done")
        log("ok: stems added to the workspace in order")
        assert app.yt_btn.cget("text") == "Done"
        t0 = time.time()
        while app.yt_btn.cget("text") != "Split…":
            assert time.time() - t0 < 10, "button did not go back to normal"
            yield 0.3
        log("ok: header button shows Done, then returns to normal")
        pop.cancel_or_back()
        app.clear_all()
        yield 0.2
        log("GUI SMOKETEST PASSED")
        app.smoketest_exit = 0

    gen = steps()

    def pump():
        try:
            delay = next(gen)
            app.root.after(int(delay * 1000), pump)
        except StopIteration:
            app.root.after(300, app.close)
        except Exception:
            log("FAILED:\n" + traceback.format_exc())
            try:
                shot("failure")
            except Exception:
                pass
            app.smoketest_exit = 1
            app.root.after(300, app.close)

    pump()


def yt_selftest(url, out_dir):
    """Download one real YouTube video (original only). Informational in the build."""
    import splitter
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = out / "yt_selftest.txt"
    try:
        info = splitter.fetch_info(url)
        o = splitter.default_settings()
        o["out"] = {"original": True, "karaoke": False, "stems": False, "stems6": False}
        o["out_root"] = str(out)
        res = splitter.run(url, "", o)
        p = res["files"]["original"]
        report.write_text(f"ok: '{info['title']}' {info['quality']} -> {p.name} "
                          f"({p.stat().st_size // 1024} KB, {engine.probe_seconds(p):.1f} s)\nYT SELFTEST PASSED\n",
                          encoding="utf-8")
        return 0
    except Exception:
        report.write_text("FAILED:\n" + traceback.format_exc(), encoding="utf-8")
        return 1
