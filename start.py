"""NiSH Player's starter: picks which app code to run, then runs it.

The installed app has two layers:
- the engine, built into NiSHPlayer.exe and _internal: Python, PyTorch, ffmpeg, the AI models, ...
  It changes only with a full download (a new "base").
- the app itself (our code: functionality and design), a folder of Python files: the one shipped in
  _internal/nish_app, or a newer one installed from the cogwheel menu into
  %LOCALAPPDATA%\\NiSH Player\\app\\<version>\\ (see apppack.py).

A downloaded app is used when it was made for this base and is newer than the shipped one. If it
fails to start - an error before the window is up, or two starts in a row that never got the window
up - it is marked bad and the one before it is used (in the end the shipped one).

This file only uses the standard library and stays the same between app updates: keep it small.
"""
import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

FORMAT = 2            # app pack layout (pack.json "format")
TRIES = 2             # starts without reaching the window before a downloaded app is marked bad
BUNDLED = "nish_app"  # the shipped app's folder in _internal


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v or "")))


def bundled_dir():
    if os.environ.get("NISH_TEST_BUNDLED"):                 # tests
        return Path(os.environ["NISH_TEST_BUNDLED"])
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / BUNDLED
    return Path(__file__).resolve().parent                  # running from source: this folder


def user_root():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "NiSH Player" / "app"


def read_info(folder):
    """pack.json of an app folder, or None if it isn't one."""
    try:
        info = json.loads((Path(folder) / "pack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if info.get("format") != FORMAT or not vkey(info.get("version")) or not (Path(folder) / "app.py").is_file():
        return None
    return info


def choices(bundled=None, root=None):
    """App folders to try, best first; the shipped one last."""
    bundled = Path(bundled or bundled_dir())
    root = Path(root or user_root())
    shipped = read_info(bundled) or {}
    found = []
    if shipped.get("base") and root.is_dir():
        for d in root.iterdir():
            if not d.is_dir() or d.name.startswith(".") or (d / "bad").exists():
                continue
            info = read_info(d)
            if info and info.get("base") == shipped["base"] and vkey(info["version"]) > vkey(shipped.get("version")):
                found.append((vkey(info["version"]), d))
    found.sort(reverse=True)
    return [d for _, d in found] + [bundled]


def mark_bad(folder, why):
    try:
        (Path(folder) / "bad").write_text(why[-4000:] or "didn't start", encoding="utf-8")
        (Path(folder) / "starting").unlink(missing_ok=True)
    except OSError:
        pass


def pick(bundled=None, root=None, track=True):
    """The folder to run. With track, a downloaded one gets a start counter (apppack.started() clears it)."""
    for folder in choices(bundled, root):
        if folder == Path(bundled or bundled_dir()) or not track:
            return folder
        marker = folder / "starting"
        try:
            tries = int(marker.read_text(encoding="utf-8").strip() or 0) if marker.exists() else 0
        except (OSError, ValueError):
            tries = TRIES
        if tries >= TRIES:
            mark_bad(folder, f"didn't reach the window in {TRIES} starts in a row")
            continue
        try:
            marker.write_text(str(tries + 1), encoding="utf-8")
        except OSError:
            pass
        return folder
    return Path(bundled or bundled_dir())


def restart(args):
    cmd = [sys.executable] + ([] if getattr(sys, "frozen", False) else [str(Path(__file__).resolve())]) + args
    subprocess.Popen(cmd, close_fds=True)


def main():
    args = sys.argv[1:]
    forced = None
    if "--app-dir" in args:                       # tests: run this app folder
        i = args.index("--app-dir")
        forced = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) >= 3 and args[0] == "--app-pack-check":
        forced = Path(args[1])                    # check a downloaded app in this engine (apppack.check_here)
    plain = not any(a.startswith("--") and a != "--wait-pid" for a in args)   # a normal start (maybe with files)
    folder = forced or pick(track=plain)
    downloaded = forced is None and folder != bundled_dir()
    os.environ["NISH_APP_DIR"] = str(folder)
    os.environ["NISH_APP_FALLBACK"] = "1" if downloaded and plain else ""
    sys.path.insert(0, str(folder))
    sys.argv = [sys.argv[0]] + args
    try:
        import app
        app.main(sys.argv)
    except SystemExit:
        raise
    except BaseException:
        if downloaded and plain and (folder / "starting").exists():
            mark_bad(folder, traceback.format_exc())
            restart(args)                         # start again with the app before it
            return
        raise


if __name__ == "__main__":
    main()
