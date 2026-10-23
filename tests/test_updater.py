"""Updater, settings and single-instance tests. The folder swap itself runs only on Windows (PowerShell).

Run:  python tests/test_updater.py
"""
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import settings  # noqa: E402
import updater  # noqa: E402


def ok(msg):
    print("ok:", msg)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="nish-upd-"))
    settings.FILE = tmp / "settings.json"

    # versions
    assert updater.version_text("v1.3.0") == "1.3.0"
    assert updater.version_text("v1.3.0-yt2026.10.10") == "1.3.0 · YouTube fix 2026.10.10"
    assert updater.current_tag().startswith("v")
    ok(f"version text, this build is {updater.current_tag()}")

    # export folder: Desktop by default, then whatever the user picked
    assert settings.export_folder() == settings.desktop()
    pick = tmp / "My exports"
    pick.mkdir()
    settings.set_export_folder(pick)
    assert settings.export_folder() == str(pick)
    pick.rmdir()                                  # folder gone (e.g. USB stick removed) -> Desktop again
    assert settings.export_folder() == settings.desktop()
    ok(f"export folder: Desktop ({settings.desktop()}) by default, remembers the user's choice")

    # YouTube failures: an update is suggested after five on the same day
    for _ in range(4):
        settings.note_yt_failure("2026-10-19")
    assert not settings.suggest_update("2026-10-19")
    assert settings.note_yt_failure("2026-10-19") == 5 and settings.suggest_update("2026-10-19")
    assert not settings.suggest_update("2026-10-20")
    assert settings.note_yt_failure("2026-10-20") == 1
    ok("update suggested after 5 failed YouTube extractions on one day, resets the next day")

    # unpack a release zip into '<app>.new' next to the app
    app_dir = tmp / "NiSHPlayer"
    app_dir.mkdir()
    (app_dir / "NiSHPlayer.exe").write_text("old")
    (app_dir / "_internal").mkdir()
    (app_dir / "_internal" / "old.txt").write_text("old")
    z = tmp / "NiSHPlayer-windows.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("NiSHPlayer/NiSHPlayer.exe", "new")
        f.writestr("NiSHPlayer/_internal/new.txt", "new")
        f.writestr("NiSHPlayer/build_tag.txt", "v9.9.9")
    stage = updater.unpack(z, app_dir)
    assert stage == tmp / "NiSHPlayer.new" and (stage / "NiSHPlayer.exe").read_text() == "new"
    ok("release zip unpacked next to the app")

    if os.name == "nt":
        # the real swap: wait for the 'app' to exit, swap folders, keep nothing old behind
        dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
        script = updater.write_script(app_dir, stage, dummy.pid, restart=False)
        p = updater.run_script(script)
        p.wait(timeout=120)
        log = tmp / "NiSHPlayer.update.log"
        print(log.read_text(encoding="utf-8") if log.exists() else "(no log)")
        psout = Path(str(script) + ".out.txt")
        print("PowerShell:", psout.read_text(errors="replace") if psout.exists() else "(no output file)",
              "exit", p.returncode)
        assert dummy.poll() is not None, "the helper should wait for the app to close"
        assert (app_dir / "NiSHPlayer.exe").read_text() == "new"
        assert (app_dir / "_internal" / "new.txt").exists() and not (app_dir / "_internal" / "old.txt").exists()
        assert not stage.exists() and not (tmp / "NiSHPlayer.old").exists()
        ok("PowerShell helper waited for the app, swapped in the new version and removed the old one")

        # rollback: the new version has vanished (e.g. removed by antivirus) -> the old one is put back
        stage = updater.unpack(z, app_dir)
        (app_dir / "NiSHPlayer.exe").write_text("current")
        script = updater.write_script(app_dir, stage, os.getpid() + 999999, restart=False)
        import shutil
        shutil.rmtree(stage)
        updater.run_script(script, wait=True)
        print(log.read_text(encoding="utf-8") if log.exists() else "(no log)")
        assert (app_dir / "NiSHPlayer.exe").read_text() == "current", "old version must be restored"
        assert not (tmp / "NiSHPlayer.old").exists()
        ok("a failed swap puts the old version back")
    else:
        script = updater.write_script(app_dir, stage, 1234, restart=False)
        text = script.read_text(encoding="utf-8-sig")
        assert "Wait-Process -Id 1234" in text and "NiSHPlayer.old" in text
        ok("helper script written (swap is tested on Windows)")

    # one app at a time: a second start hands its files to the running one
    import instance
    instance.PORT_FILE = tmp / "instance.port"
    assert not instance.hand_off(["x.nish"]), "nobody is listening yet"
    got = []
    srv = instance.serve(got.append)
    assert srv is not None and instance.PORT_FILE.exists()
    assert instance.hand_off([str(tmp / "My Song.nish")])
    assert got and Path(got[0][0]).name == "My Song.nish", got
    assert instance.hand_off([])                    # plain start: just bring the window forward
    instance.stop(srv)
    assert not instance.PORT_FILE.exists() and not instance.hand_off(["x.nish"])
    ok("second start hands its files to the running app")
    if os.name == "nt":
        ok(f"file type registration runs only in the built app: {instance.register_file_type()}")

    print("UPDATER TESTS PASSED")


if __name__ == "__main__":
    main()
