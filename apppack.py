"""App updates: the app itself (functionality and design) and YouTube support in one small download
(~3 MB) instead of the full ~600 MB app.

The full download holds the engine (Python, PyTorch, ffmpeg, the AI models) and rarely changes; its
version is the "base" (the BASE file). Our own code is a folder of Python files that start.py loads at
start: the shipped one (_internal/nish_app) or a newer one from here (%LOCALAPPDATA%\\NiSH Player\\
app\\<version>\\). An update is published on GitHub as the 'app-update' release (a pre-release, so the
full-update check never sees it):

    app-update.json   {format, version, youtube, base, asset, size, sha256}
    <asset>.zip       app/      our code (pack.json: format 2, version, base)
                      youtube/  a YouTube pack (ytpack.py)

An update only fits the base it was made and tested for. Its YouTube part is used from the next
YouTube download (ytpack.py); its app part from the next start ("Restart now" in the cogwheel menu).
If a new app fails to start, start.py goes back to the previous one.
"""
import compileall
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

import ytpack
from ytpack import vkey

FORMAT = 2
RELEASE = "app-update"
MANIFEST = "app-update.json"
CHECK_TIMEOUT = 180


# ---------- this installation ----------

def here():
    """The folder of the app code that is running."""
    return Path(os.environ.get("NISH_APP_DIR") or Path(__file__).resolve().parent)


def bundled_dir():
    """The app shipped with the full download (None when running from source)."""
    if os.environ.get("NISH_TEST_BUNDLED"):
        return Path(os.environ["NISH_TEST_BUNDLED"])
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "nish_app" if base else None


def read_info(folder):
    """pack.json of an app folder (format 2), else None."""
    try:
        info = json.loads((Path(folder) / "pack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if info.get("format") != FORMAT or not vkey(info.get("version")) or not (Path(folder) / "app.py").is_file():
        return None
    return info


def base():
    """The base (full download) this installation is, e.g. '2.1.0'; None when running from source."""
    b = bundled_dir()
    info = read_info(b) if b else None
    return info.get("base") if info else None


def version():
    """The version of the app code that is running, e.g. '2.1.3'."""
    info = read_info(here())
    if info:
        return info["version"]
    f = Path(__file__).resolve().parent / "VERSION"
    try:
        return f.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def user_root():
    import engine
    return engine.DATA_DIR / "app"


def started():
    """The app is up: a downloaded app that got this far is good (clears start.py's start counter)."""
    try:
        (here() / "starting").unlink(missing_ok=True)
    except OSError:
        pass


# ---------- checking an app in this engine (run in a new process by install and by the build) ----------

def modules(folder):
    return sorted(p.stem for p in Path(folder).glob("*.py") if p.stem != "start")


def check_here(folder, result, youtube=None):
    """Import every module of the app in `folder` the way a start would (this process was started with
    it, see start.py), compile it, and load the YouTube pack `youtube` with it. Writes 'ok <version>'
    or the error to `result`."""
    out = Path(result)
    try:
        folder = Path(folder).resolve()
        info = read_info(folder)
        assert info, "not an app folder"
        names = modules(folder)
        for name in names:
            mod = importlib.import_module(name)
            assert Path(mod.__file__).resolve().parent == folder, f"{name} came from {mod.__file__}"
        compileall.compile_dir(str(folder), quiet=1, force=True)
        text = f"ok {info['version']} ({len(names)} modules)"
        if youtube:
            yt_result = out.with_name(out.name + ".yt")
            ytpack.check_here(youtube, yt_result)
            yt = yt_result.read_text(encoding="utf-8")
            yt_result.unlink(missing_ok=True)
            assert yt.startswith("ok "), yt
            text += f", YouTube {yt[3:].strip()}"
        out.write_text(text + "\n", encoding="utf-8")
        return 0
    except BaseException:
        out.write_text("FAILED:\n" + traceback.format_exc(), encoding="utf-8")
        return 1


def check_in_new_process(folder, youtube=None):
    """(ok, details): check_here in a fresh run of this app's engine with the new app code."""
    folder = Path(folder)
    result = folder.parent / (folder.name + ".check.txt")
    args = ["--app-pack-check", str(folder), str(result)] + ([str(youtube)] if youtube else [])
    if getattr(sys, "frozen", False):
        cmd = [sys.executable] + args
    else:
        cmd = [sys.executable, str(Path(__file__).resolve().parent / "start.py")] + args
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        subprocess.run(cmd, timeout=CHECK_TIMEOUT, creationflags=flags, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        text = result.read_text(encoding="utf-8") if result.is_file() else "the check didn't run"
    except Exception as e:
        text = f"the check didn't finish: {e}"
    finally:
        result.unlink(missing_ok=True)
    return text.startswith("ok "), text


# ---------- getting an update ----------

def manifest_url():
    import updater
    return f"https://github.com/{updater.REPO}/releases/download/{RELEASE}/{MANIFEST}"


def newest_version():
    """The running app's version, or the one installed for the next start if that is newer."""
    return max(filter(None, (version(), installed())), key=vkey, default=None)


def check():
    """The newest published update. Adds: fits (made for this base), app_newer, yt_newer, newer, url."""
    import updater
    with updater._open(manifest_url()) as r:
        m = json.loads(r.read().decode("utf-8"))
    if m.get("format") != FORMAT or not vkey(m.get("version")) or not re.fullmatch(r"[\w.-]+\.zip", m.get("asset", "")):
        raise RuntimeError("The published update isn't readable by this version.")
    fits = bool(base()) and m.get("base") == base()
    m["fits"] = fits
    m["app_newer"] = fits and vkey(m["version"]) > vkey(newest_version())
    m["yt_newer"] = fits and vkey(m.get("youtube")) > vkey(ytpack.version())
    m["newer"] = m["app_newer"] or m["yt_newer"]
    m["url"] = f"https://github.com/{updater.REPO}/releases/download/{RELEASE}/{m['asset']}"
    return m


def install(m, progress=lambda f: None, cancelled=lambda: False, checking=lambda: None, check=None):
    """Download, verify, check and install the update check() described. Returns {'app', 'youtube'}:
    which parts were installed (the app part is used from the next start, YouTube right away)."""
    import updater
    root = user_root()
    root.mkdir(parents=True, exist_ok=True)
    zpath = root / m["asset"]
    tmp = root / f".{m['version']}.new"
    done = {"app": False, "youtube": False}
    try:
        updater.download(m["url"], zpath, progress=progress, cancelled=cancelled)
        checking()                                   # downloaded: now verifying (no cancelling any more)
        if m.get("sha256") and ytpack.sha256(zpath) != m["sha256"].lower():
            raise RuntimeError("The update was damaged on the way. Try again.")
        shutil.rmtree(tmp, ignore_errors=True)
        ytpack.unpack(zpath, tmp)
        info = read_info(tmp / "app")
        yt = ytpack.read_info(tmp / "youtube")
        if not info or info["version"] != m["version"] or info.get("base") != base() or not yt:
            raise RuntimeError("The update is incomplete.")
        want_app = vkey(info["version"]) > vkey(newest_version())
        want_yt = vkey(yt["version"]) > vkey(ytpack.version())
        if want_app:
            ok, details = (check or check_in_new_process)(tmp / "app", tmp / "youtube")
        elif want_yt:
            ok, details = ytpack.check_in_new_process(tmp / "youtube")
        else:
            ok, details = True, ""
        if not ok:
            raise RuntimeError("This update doesn't work with your installation. The next one will.\n"
                               + details[-300:])
        if want_yt:
            dest = ytpack.user_root() / yt["version"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(dest, ignore_errors=True)
            os.replace(tmp / "youtube", dest)
            done["youtube"] = True
        if want_app:
            dest = root / info["version"]
            shutil.rmtree(dest, ignore_errors=True)
            os.replace(tmp / "app", dest)
            done["app"] = True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for p in (zpath, zpath.with_suffix(".part")):
            try:
                p.unlink()
            except OSError:
                pass
    if done["youtube"]:
        ytpack.prune()
    prune()
    return done


def installed():
    """The newest downloaded app that fits this base and is newer than the running one (it runs from
    the next start), else None."""
    import start
    b = bundled_dir()
    if not b:
        return None
    best = start.choices(b, user_root())[0]
    info = read_info(best)
    return info["version"] if best != b and info and vkey(info["version"]) > vkey(version()) else None


def prune():
    """Remove downloaded apps that will never run again: not the newest that fits, not the running one."""
    root = user_root()
    b = bundled_dir()
    if not root.is_dir() or not b:
        return
    import start
    keep = {start.choices(b, root)[0].resolve(), here().resolve()}
    for d in root.iterdir():
        if d.is_dir() and not d.name.startswith(".") and d.resolve() not in keep:
            shutil.rmtree(d, ignore_errors=True)


# ---------- restarting ----------

def restart_command(paths=()):
    """The command that starts the app again once this process has ended, opening `paths`."""
    args = ["--wait-pid", str(os.getpid())] + [str(p) for p in paths]
    if getattr(sys, "frozen", False):
        return [sys.executable] + args
    return [sys.executable, str(Path(__file__).resolve().parent / "start.py")] + args


def restart(paths=()):
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(restart_command(paths), creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL)


def wait_for_exit(pid, timeout=30):
    """Wait until process `pid` has ended (the app being restarted)."""
    import time
    pid = int(pid)
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000, False, pid)           # SYNCHRONIZE
        if h:
            k.WaitForSingleObject(h, int(timeout * 1000))
            k.CloseHandle(h)
        return
    end = time.time() + timeout
    while time.time() < end:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
