"""GUI smoke test, used by the GitHub build:  NiSHPlayer.exe --gui-smoketest <folder>

Makes a small test song, loads it, clicks through every control, exports, and writes
gui_smoketest.txt (plus screenshots) to <folder>. Exit code 0 = passed.
"""
import time
import traceback
from pathlib import Path

import numpy as np

import engine


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
        yield 0.5
        t0 = time.time()
        while app.player.render_busy or any(t.buf_key != (0.85, -2.0) for t in app.player.tracks):
            assert time.time() - t0 < 90, "speed/pitch render timed out"
            yield 0.2
        n0 = app.player.source_length()
        assert abs(app.player.length() / n0 - 1 / 0.85) < 0.02
        assert abs(app.player.position() - 0.5) < 0.02
        assert app.speed_val.cget("text") == "0.85×" and app.pitch_val.cget("text") == "−2 st"
        log(f"ok: live speed 0.85x / pitch -2 st in {time.time() - t0:.1f}s, playhead kept")

        # manual fine tune, then Auto 440 overrides it
        app.fine_slider.set(12)
        app.on_fine(12)
        assert app.fine_val.cget("text") == "+12 ct"
        app.auto_var.set(True)
        app.on_auto()
        t0 = time.time()
        while app.analysing:
            assert time.time() - t0 < 60, "Auto 440 analysis timed out"
            yield 0.2
        yield 0.5
        corr, a_hz, conf = app.auto_result
        assert 9 <= corr <= 16 and abs(a_hz - 436.8) < 1.5, app.auto_result
        assert app.fine_slider.cget("state") == "disabled"
        assert abs(app.fine_slider.get() - corr) <= 1
        assert "Set by Auto 440" in app.fine_info.cget("text"), app.fine_info.cget("text")
        log(f"ok: Auto 440 detected A = {a_hz:.1f} Hz -> {corr:+.1f} ct, slider locked: "
            f"{app.fine_info.cget('text')}")
        t0 = time.time()
        want = round(-2 + app.current_cents() / 100, 6)
        while app.player.render_busy or any(t.buf_key[1] != want for t in app.player.tracks):
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

        # export dialog: warning only here (pitch shift + Auto 440)
        app.open_export()
        yield 0.8
        d = app.export_dialog
        assert d is not None and d.has_warning, "export warning missing"
        assert d.tags == ["0.85x", "-2st", "440hz"], d.tags
        assert d.name_var.get() == "My Song_mix_0.85x_-2st_440hz", d.name_var.get()
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
        assert mp3.name == "My Song_mix_0.85x_-2st_440hz.mp3" and abs(secs - 8 / 0.85) < 0.2, (mp3, secs)
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
        assert names == ["My Song_DRM_0.85x_-2st_440hz.wav", "My Song_OTH_0.85x_-2st_440hz.wav",
                         "My Song_VOX_0.85x_-2st_440hz.wav"], names
        log(f"ok: exported each track: {names}")
        d.close()
        yield 0.2

        # Auto 440 off -> manual value comes back
        app.auto_var.set(False)
        app.on_auto()
        yield 0.2
        assert app.fine_val.cget("text") == "+12 ct" and app.fine_slider.cget("state") == "normal"
        log("ok: Auto 440 off restores the manual fine tune")

        # remove and clear
        app.remove_lane(drums)
        yield 0.2
        assert len(app.lanes) == 2 and len(app.player.tracks) == 2
        app.clear_all()
        yield 0.2
        assert not app.lanes and app.count_lbl.cget("text") == "NO TRACKS"
        log("ok: remove track and clear all")
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
