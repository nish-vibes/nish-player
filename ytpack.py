"""YouTube support as a small, separately updated "pack": yt-dlp and its YouTube challenge solver
(yt-dlp-ejs, which yt-dlp needs in an exact version, so they travel together).

YouTube changes often and yt-dlp follows within days, while the rest of the app (AI models, PyTorch,
ffmpeg: ~600 MB) rarely changes. So yt-dlp is not built into NiSHPlayer.exe:

- The app ships with a pack in its own folder (_internal/youtube), so YouTube works offline from the start.
- Newer packs (~3 MB) are published weekly on GitHub (the 'youtube-pack' release, a pre-release so the
  app update check never sees it). check() and install() fetch one into %LOCALAPPDATA%\\NiSH Player\\
  youtube\\<version>\\ - the app folder is never touched and nothing restarts.
- use() imports yt-dlp from the newest pack that works. A pack that fails to load is marked bad and the
  one before it is used (in the end the shipped one). Switching happens only while no YouTube work runs.
- The things yt-dlp relies on (web requests, certificates, ...) stay in the app, so packs are plain Python.

Running from source without packs, yt-dlp is imported from the Python installation as usual.
"""
import contextlib
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import traceback
import zipfile
from pathlib import Path

FORMAT = 1                      # the pack layout; a pack with another format is ignored
PACKAGES = ("yt_dlp", "yt_dlp_ejs")
RELEASE = "youtube-pack"        # the GitHub release (tag) the packs are published on
MANIFEST = "youtube-pack.json"  # its description: version, file name, size, sha256, oldest app it works with
CHECK_TIMEOUT = 120


# ---------- where packs are ----------

def bundled_dir():
    """The pack shipped with the app (None when running from source)."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "youtube" if base else None


def user_root():
    import engine
    return engine.DATA_DIR / "youtube"


def vkey(v):
    """'2026.10.26' -> (2026, 10, 26), for comparing versions."""
    return tuple(int(x) for x in re.findall(r"\d+", str(v or "")))


def app_version():
    import updater
    v = updater.current_tag().lstrip("v").split("-", 1)[0]
    return v if vkey(v) else None


def read_info(folder):
    """pack.json of a usable pack folder, else None (missing, damaged, other format, or marked bad)."""
    folder = Path(folder)
    try:
        info = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (info.get("format") != FORMAT or not vkey(info.get("version"))
            or not all((folder / p / "__init__.py").is_file() for p in PACKAGES) or (folder / "bad").exists()):
        return None
    app = app_version()
    if app and vkey(info.get("min_app")) > vkey(app):
        return None              # made for a newer app
    return info


def packs():
    """[(folder, info)] of every usable pack, newest first (the shipped one wins a tie)."""
    found = []
    b = bundled_dir()
    if b and read_info(b):
        found.append((b, read_info(b)))
    root = user_root()
    if root.is_dir():
        for d in root.iterdir():
            info = d.is_dir() and not d.name.startswith(".") and read_info(d)
            if info:
                found.append((d, info))
    found.sort(key=lambda fi: (vkey(fi[1]["version"]), fi[0] == b), reverse=True)
    return found


def version():
    """The yt-dlp version in use (or that will be used), e.g. '2026.10.26'; None if there is none."""
    p = packs()
    if p:
        return p[0][1]["version"]
    try:
        from importlib.metadata import version as dist_version
        return dist_version("yt-dlp")
    except Exception:
        return None


# ---------- using a pack ----------

_lock = threading.RLock()
_users = 0          # YouTube operations running right now (no switching while > 0)
_loaded = None      # folder of the pack that is imported (or "" for the Python installation)


def _unload():
    for name in list(sys.modules):
        if name.split(".", 1)[0] in PACKAGES:
            del sys.modules[name]
    for d, _ in packs() + [(bundled_dir(), None)]:
        while d and str(d) in sys.path:
            sys.path.remove(str(d))
    if _loaded:
        while str(_loaded) in sys.path:
            sys.path.remove(str(_loaded))
    importlib.invalidate_caches()


def _import_from(folder):
    _unload()
    if folder:
        sys.path.insert(0, str(folder))
    importlib.invalidate_caches()
    import yt_dlp
    if folder:
        import yt_dlp_ejs  # noqa: F401  (a pack's solver must load too)
    return yt_dlp


def mark_bad(folder, why=""):
    """Never use this downloaded pack again (the shipped one is never marked)."""
    if folder and Path(folder) != bundled_dir():
        try:
            (Path(folder) / "bad").write_text(why or "failed to load", encoding="utf-8")
        except OSError:
            pass


def _ensure():
    global _loaded
    order = [f for f, _ in packs()]
    if _loaded is not None and "yt_dlp" in sys.modules and (_users > 0 or not order or order[0] == _loaded):
        return sys.modules["yt_dlp"]
    for folder in order:
        try:
            mod = _import_from(folder)
            _loaded = folder
            return mod
        except Exception:
            traceback.print_exc()
            mark_bad(folder, traceback.format_exc()[-2000:])
    mod = _import_from(None)          # running from source: the Python installation's yt-dlp
    _loaded = ""
    return mod


@contextlib.contextmanager
def use():
    """with ytpack.use() as yt_dlp: ... - yt-dlp from the newest pack that works."""
    global _users
    with _lock:
        mod = _ensure()
        _users += 1
    try:
        yield mod
    finally:
        with _lock:
            _users -= 1


# ---------- checking a pack (also run by the build against the built app) ----------

def check_here(folder, result):
    """Load the pack in this (fresh) process the way a YouTube download does, including the YouTube
    extractor and the challenge solver's scripts. Writes 'ok <version>' or the error to `result`."""
    out = Path(result)
    try:
        info = json.loads((Path(folder) / "pack.json").read_text(encoding="utf-8"))
        yt_dlp = _import_from(folder)
        assert Path(yt_dlp.__file__).resolve().is_relative_to(Path(folder).resolve()), yt_dlp.__file__
        from yt_dlp.version import __version__
        assert __version__ == info["version"], (__version__, info["version"])
        import yt_dlp.extractor.youtube  # noqa: F401
        import yt_dlp.networking  # noqa: F401
        import yt_dlp.postprocessor  # noqa: F401
        from yt_dlp.extractor.youtube.jsc._builtin import ejs  # noqa: F401
        import yt_dlp_ejs.yt.solver as solver
        assert solver.core() and solver.lib(), "the challenge solver's scripts are missing"
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            assert ydl.get_info_extractor("Youtube")
        out.write_text(f"ok {__version__}\n", encoding="utf-8")
        return 0
    except Exception:
        out.write_text("FAILED:\n" + traceback.format_exc(), encoding="utf-8")
        return 1


def check_in_new_process(folder):
    """(ok, details): check_here in a separate run of this app, so the check sees exactly what a fresh
    start would (and nothing half-loaded stays behind in the running app)."""
    folder = Path(folder)
    result = folder.parent / (folder.name + ".check.txt")
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--yt-pack-check", str(folder), str(result)]
    else:
        cmd = [sys.executable, str(Path(__file__).resolve().parent / "app.py"), "--yt-pack-check",
               str(folder), str(result)]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        subprocess.run(cmd, timeout=CHECK_TIMEOUT, creationflags=flags, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        text = result.read_text(encoding="utf-8") if result.is_file() else "the check didn't run"
    except Exception as e:
        text = f"the check didn't finish: {e}"
    finally:
        try:
            result.unlink()
        except OSError:
            pass
    return text.startswith("ok "), text


# ---------- getting a newer pack ----------

def manifest_url():
    import updater
    return f"https://github.com/{updater.REPO}/releases/download/{RELEASE}/{MANIFEST}"


def check():
    """The newest published pack: {"version", "newer", "size", "url", ...}. 'newer' only when it is
    newer than the one in use and works with this app."""
    import updater
    with updater._open(manifest_url()) as r:
        m = json.loads(r.read().decode("utf-8"))
    if m.get("format") != FORMAT or not vkey(m.get("version")) or not re.fullmatch(r"[\w.-]+\.zip", m.get("asset", "")):
        raise RuntimeError("The published YouTube fix isn't readable by this version.")
    app = app_version()
    fits = not app or vkey(m.get("min_app")) <= vkey(app)
    m["newer"] = fits and vkey(m["version"]) > vkey(version())
    m["needs_app_update"] = not fits
    m["url"] = f"https://github.com/{updater.REPO}/releases/download/{RELEASE}/{m['asset']}"
    return m


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unpack(zip_path, dest):
    """Unpack a pack zip into `dest` (refusing paths that would land outside it)."""
    dest = Path(dest)
    base = dest.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            target = (dest / n).resolve()
            if not target.is_relative_to(base):
                raise RuntimeError("The YouTube fix contains an unexpected file path.")
        z.extractall(dest)


def install(m, progress=lambda f: None, cancelled=lambda: False, check=None, checking=lambda: None):
    """Download, verify and unpack the pack described by check()'s result. Returns its folder.
    It is used from the next YouTube download on (or right away if none is running)."""
    import updater
    root = user_root()
    root.mkdir(parents=True, exist_ok=True)
    ver = m["version"]
    zpath = root / m["asset"]
    tmp = root / f".{ver}.new"
    final = root / ver
    try:
        updater.download(m["url"], zpath, progress=progress, cancelled=cancelled)
        checking()                   # downloaded: now verifying (can't be cancelled any more)
        if m.get("sha256") and sha256(zpath) != m["sha256"].lower():
            raise RuntimeError("The YouTube fix was damaged on the way. Try again.")
        shutil.rmtree(tmp, ignore_errors=True)
        unpack(zpath, tmp)
        info = read_info(tmp)
        if not info or info["version"] != ver:
            raise RuntimeError("The YouTube fix is incomplete.")
        ok, details = (check or check_in_new_process)(tmp)
        if not ok:
            raise RuntimeError("This YouTube fix doesn't work with your version of NiSH Player. "
                               "Its next version will.\n" + details[-300:])
        shutil.rmtree(final, ignore_errors=True)
        os.replace(tmp, final)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            zpath.unlink()
        except OSError:
            pass
        try:
            zpath.with_suffix(".part").unlink()
        except OSError:
            pass
    prune()
    return final


def prune():
    """Remove downloaded packs that will never be used again: older than the newest usable one (except
    the one imported right now) and broken ones."""
    root = user_root()
    if not root.is_dir():
        return
    usable = packs()
    keep = {usable[0][0]} if usable else set()
    if _loaded:
        keep.add(Path(_loaded))
    for d in root.iterdir():
        if d.is_dir() and d not in keep and not d.name.startswith("."):
            shutil.rmtree(d, ignore_errors=True)
