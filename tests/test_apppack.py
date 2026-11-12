"""App update tests: which app code start.py runs, going back from one that fails to start,
checking for and installing an update (app + YouTube), and checking new app code in a new process.

Run:  python tests/test_apppack.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
TMP = Path(tempfile.mkdtemp(prefix="nish-apppack-"))
os.environ["LOCALAPPDATA"] = str(TMP / "local")
BUNDLED = TMP / "exe" / "nish_app"
os.environ["NISH_TEST_BUNDLED"] = str(BUNDLED)

import engine  # noqa: E402
import start  # noqa: E402

engine.DATA_DIR = TMP / "local" / "NiSH Player"
import apppack  # noqa: E402
import ytpack  # noqa: E402

ytpack.bundled_dir = lambda: TMP / "exe" / "youtube"


def ok(msg):
    print("ok:", msg)


def fake_app(folder, version, base="2.1.0", code=None):
    """A tiny app folder whose main() writes which version ran."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "app.py").write_text(code or (
        "import os, pathlib\n"
        "def main(argv):\n"
        f"    pathlib.Path(os.environ['NISH_TEST_OUT']).write_text({version!r} + ' ' + ' '.join(argv[1:]))\n"
        "    (pathlib.Path(os.environ['NISH_APP_DIR']) / 'starting').unlink(missing_ok=True)\n"), encoding="utf-8")
    (folder / "pack.json").write_text(json.dumps({"format": 2, "version": version, "base": base}), encoding="utf-8")
    return folder


def fake_yt(folder, version):
    folder = Path(folder)
    for p in ytpack.PACKAGES:
        (folder / p).mkdir(parents=True, exist_ok=True)
        (folder / p / "__init__.py").write_text(f"PACK = {version!r}\n", encoding="utf-8")
    (folder / "pack.json").write_text(json.dumps({"format": 1, "version": version, "ejs": "0.8.0",
                                                  "min_app": "2.0.0"}), encoding="utf-8")
    return folder


def run_start(*args, wait_for=None):
    out = TMP / "ran.txt"
    out.unlink(missing_ok=True)
    env = dict(os.environ, NISH_TEST_OUT=str(out))
    subprocess.run([sys.executable, str(ROOT / "start.py"), *args], env=env, timeout=60)
    for _ in range(100):                                   # a restart runs in a second process
        if out.exists() and (not wait_for or out.read_text().startswith(wait_for)):
            break
        time.sleep(0.1)
    return out.read_text() if out.exists() else None


def main():
    root = start.user_root()
    assert root == engine.DATA_DIR / "app" == apppack.user_root()

    # --- which app start.py runs ---
    fake_app(BUNDLED, "2.1.0")
    assert start.choices() == [BUNDLED]
    fake_app(root / "2.1.1", "2.1.1")
    fake_app(root / "2.1.5", "2.1.5", base="2.0.0")           # made for another base: ignored
    fake_app(root / "2.0.9", "2.0.9")                          # older than the shipped one: ignored
    fake_app(root / "2.1.3", "2.1.3")
    (root / "2.1.3" / "bad").write_text("x")                   # marked bad: ignored
    (root / "2.1.4").mkdir()                                   # incomplete: ignored
    assert start.choices() == [root / "2.1.1", BUNDLED], start.choices()
    ok("start.py: the newest downloaded app made for this base wins (not older, other-base, bad or incomplete)")

    # --- start counter: two starts that never reach the window -> bad ---
    assert start.pick() == root / "2.1.1" and (root / "2.1.1" / "starting").read_text() == "1"
    assert start.pick() == root / "2.1.1" and (root / "2.1.1" / "starting").read_text() == "2"
    assert start.pick() == BUNDLED and (root / "2.1.1" / "bad").is_file()
    assert start.pick(track=False) == BUNDLED
    ok("start.py: a downloaded app that doesn't reach the window twice in a row is marked bad")

    # --- real starts (a new process, like the exe) ---
    fake_app(root / "2.1.6", "2.1.6")
    assert run_start("song.nish") == "2.1.6 song.nish"
    assert not (root / "2.1.6" / "starting").exists()          # its main() cleared the counter
    fake_app(root / "2.1.7", "2.1.7", code="raise ImportError('this engine has no foo')\n")
    assert run_start("a.flac", wait_for="2.1.6") == "2.1.6 a.flac", "should go back to 2.1.6"
    assert "no foo" in (root / "2.1.7" / "bad").read_text()
    assert run_start("--app-dir", str(BUNDLED), "x") == "2.1.0 x"          # forced (the build's tests)
    ok("start.py in a new process: runs the newest app; one that fails to start is marked bad and the app "
       "starts again with the one before it")

    # --- what's running, what's installed ---
    for d in list(root.iterdir()):
        if d.name != "2.1.6":
            import shutil
            shutil.rmtree(d)
    os.environ["NISH_APP_DIR"] = str(BUNDLED)
    assert apppack.base() == "2.1.0" and apppack.version() == "2.1.0"
    assert apppack.installed() == "2.1.6" and apppack.newest_version() == "2.1.6"
    os.environ["NISH_APP_DIR"] = str(root / "2.1.6")
    assert apppack.version() == "2.1.6" and apppack.installed() is None
    os.environ["NISH_APP_DIR"] = str(BUNDLED)
    ok("version (running), installed (used from the next start), base")

    # --- building, checking for and installing an update ---
    import build_app_pack
    out = TMP / "pack"
    fake_yt(out / "youtube", "2099.01.01")
    ver = (ROOT / "VERSION").read_text().strip()
    m = build_app_pack.build(out)
    assert m["youtube"] == "2099.01.01" and (out / "app" / "app.py").is_file() and (out / "app" / "start.py").is_file()
    assert apppack.read_info(out / "app")["version"] == ver
    names = sorted(p.name for p in (out / "app").iterdir())
    assert "smoketest.py" in names and "pack.json" in names and "VERSION" in names
    # pretend this installation is the base the update was made for, one version behind
    fake_app(BUNDLED, "2.0.5", base=m["base"])
    for d in list(root.iterdir()):
        import shutil
        shutil.rmtree(d)
    fake_yt(TMP / "exe" / "youtube", "2026.10.26")
    man = TMP / "app-update.json"
    zpath = out / m["asset"]
    man.write_text(json.dumps(m), encoding="utf-8")
    apppack.manifest_url = lambda: man.resolve().as_uri()
    r = apppack.check()
    assert r["fits"] and r["app_newer"] and r["yt_newer"] and r["newer"], r
    assert r["url"].endswith(f"/releases/download/app-update/{m['asset']}")
    man.write_text(json.dumps({**m, "base": "9.9.9"}), encoding="utf-8")
    r2 = apppack.check()
    assert not r2["fits"] and not r2["newer"]
    man.write_text(json.dumps({**m, "asset": "../evil.exe"}), encoding="utf-8")
    try:
        apppack.check()
        raise AssertionError("odd asset accepted")
    except RuntimeError:
        pass
    ok("check: new app + YouTube for this base; another base doesn't fit; odd file names refused")

    r["url"] = zpath.resolve().as_uri()
    checked = []
    done = apppack.install(r, check=lambda a, y: (checked.append((a.name, y.name)) or True, "ok"))
    assert done == {"app": True, "youtube": True} and checked == [("app", "youtube")], (done, checked)
    assert (root / ver / "app.py").is_file() and apppack.installed() == ver
    assert ytpack.version() == "2099.01.01"
    assert not any(p.name.startswith(".") or p.suffix in (".zip", ".part") for p in root.iterdir())
    man.write_text(json.dumps(m), encoding="utf-8")
    r3 = apppack.check()
    assert not r3["newer"], "an installed update (waiting for a restart) is offered again"
    ok("install: download, sha256, unpack, check in a new process, app for the next start, YouTube right away; "
       "not offered again before the restart")

    import shutil
    shutil.rmtree(root / ver)
    try:
        apppack.install(dict(r, sha256="0" * 64), check=lambda a, y: (True, ""))
        raise AssertionError("damaged download accepted")
    except RuntimeError as e:
        assert "damaged" in str(e)
    try:
        apppack.install(r, check=lambda a, y: (False, "FAILED: no module named foo"))
        raise AssertionError("an update that failed its check was installed")
    except RuntimeError as e:
        assert "doesn't work with your installation" in str(e)
    assert apppack.installed() is None and sorted(p.name for p in root.iterdir()) == []
    ok("install refuses a damaged download and an update that fails its check (nothing left behind)")

    # --- prune ---
    fake_app(root / "2.0.6", "2.0.6", base=m["base"])
    fake_app(root / "2.0.7", "2.0.7", base=m["base"])
    fake_app(root / "2.0.8", "2.0.8", base="0.0.0")
    apppack.prune()
    assert sorted(p.name for p in root.iterdir()) == ["2.0.7"], sorted(p.name for p in root.iterdir())
    ok("prune keeps only the newest app that fits (and the running one)")

    # --- restart ---
    cmd = apppack.restart_command(["C:/x/song.nish"])
    assert cmd[-3:] == ["--wait-pid", str(os.getpid()), "C:/x/song.nish"] and cmd[1].endswith("start.py")
    t0 = time.time()
    apppack.wait_for_exit(999999, timeout=2)                   # no such process: returns at once
    assert time.time() - t0 < 1.5
    ok("restart: start.py --wait-pid <this app> <project>")

    # --- the real app code, checked in a new process (start.py --app-pack-check) ---
    del os.environ["NISH_TEST_BUNDLED"]
    good, details = apppack.check_in_new_process(out / "app")
    assert good, details
    assert list((out / "app" / "__pycache__").glob("*.pyc")), "not compiled"
    ok(f"the real app checks out in a new process: {details.strip()}")
    import importlib.util
    if importlib.util.find_spec("yt_dlp") and importlib.util.find_spec("yt_dlp_ejs"):
        import build_youtube_pack
        ytpack._unload()
        build_youtube_pack.build(TMP / "real")
        good, details = apppack.check_in_new_process(out / "app", TMP / "real" / "youtube")
        assert good, details
        ok(f"...with a real YouTube pack: {details.strip()}")
    else:
        print("skipped: app + real YouTube pack (yt-dlp isn't installed here)")
    print("APPPACK TESTS PASSED")


if __name__ == "__main__":
    main()
