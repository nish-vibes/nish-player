# PyInstaller build recipe. Run on Windows:  pyinstaller NiSHPlayer.spec
# Expects ffmpeg.exe and deno.exe in vendor/, the AI models in models/checkpoints/ (tools/build_parts.py),
# the YouTube pack in pack/youtube and the app in pack/app (tools/build_youtube_pack.py, build_app_pack.py).
#
# The exe is the engine plus start.py. Our own code (every top-level .py) is analysed so everything it
# imports gets bundled, then taken out of the exe and shipped as plain files in _internal/nish_app, so
# app updates can replace it (see start.py and apppack.py).
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

HERE = Path(SPECPATH).resolve()
OURS = sorted(p.stem for p in HERE.glob("*.py") if p.stem != "start")
datas, binaries, hiddenimports = [], [], list(OURS)
# Standard library modules a later app update might start using, bundled now so it still fits this engine.
hiddenimports += ["csv", "difflib", "textwrap", "uuid", "html", "html.parser", "xml.etree.ElementTree",
                  "statistics", "fractions", "decimal", "bisect", "heapq", "colorsys", "wave", "array", "struct",
                  "base64", "hmac", "secrets", "glob", "fnmatch", "tempfile", "calendar", "locale", "gettext",
                  "pprint", "dataclasses", "enum", "functools", "itertools", "operator", "typing", "weakref",
                  "copy", "pickle", "shelve", "configparser", "logging", "logging.handlers", "argparse",
                  "platform", "getpass", "ctypes", "ctypes.wintypes", "winreg", "msvcrt", "asyncio",
                  "concurrent.futures", "multiprocessing", "socket", "selectors", "ssl", "urllib.parse",
                  "urllib.request", "http.client", "mimetypes", "webbrowser", "unicodedata", "codecs",
                  "compileall", "importlib", "importlib.metadata", "zipfile", "tarfile", "gzip", "lzma", "bz2",
                  "sqlite3", "json", "re", "shutil", "subprocess", "threading", "queue", "hashlib", "random",
                  "math", "cmath", "datetime", "time", "zoneinfo", "string", "io", "contextlib", "traceback",
                  "inspect", "ast", "tokenize", "email", "email.message", "smtplib", "imaplib", "ftplib"]
# AI separation (Demucs)
datas += collect_data_files("demucs")
hiddenimports += collect_submodules("demucs")
# Some Demucs checkpoints were pickled with numpy 1.x paths (numpy.core.*)
hiddenimports += collect_submodules("numpy.core")
for pkg in ("customtkinter", "darkdetect", "tkinterdnd2", "sounddevice", "_sounddevice_data",
            "soundfile", "_soundfile_data"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

for exe in ("ffmpeg.exe", "deno.exe"):
    if Path("vendor", exe).exists():
        binaries.append((str(Path("vendor", exe)), "bin"))
datas.append(("assets", "assets"))
# YouTube support is a separate pack (see ytpack.py), shipped as _internal/youtube and updated on its own.
# yt-dlp is still analysed (hiddenimports) so everything it relies on gets bundled; its own modules are
# taken out of the exe below.
YT_PACKAGES = ("yt_dlp", "yt_dlp_ejs")
hiddenimports += collect_submodules("yt_dlp")
if Path("pack", "youtube", "pack.json").is_file():
    datas.append(("pack/youtube", "youtube"))
else:
    print("WARNING: no YouTube pack in pack/youtube (run tools/build_youtube_pack.py pack)")
# the AI models (both Demucs models), so splitting works on the first try and offline
if Path("models", "checkpoints").is_dir():
    datas.append(("models", "models"))

if Path("pack", "app", "pack.json").is_file():
    datas.append(("pack/app", "nish_app"))
else:
    raise SystemExit("no app in pack/app (run tools/build_app_pack.py pack)")

a = Analysis(
    ["start.py"],
    pathex=[str(HERE)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch.utils.tensorboard", "tensorboard", "matplotlib", "IPython", "jupyter", "notebook",
              "pytest", "pandas", "gradio", "hydra"],
    noarchive=False,
)
def _not_youtube(entry):
    top = entry[0].replace("\\", "/").split("/")[0].split(".")[0]
    return top not in YT_PACKAGES


def _not_ours(entry):
    name, path = entry[0], entry[1]
    return not (name.split(".")[0] in OURS and path and Path(path).resolve().parent == HERE)


a.pure = [e for e in a.pure if _not_youtube(e) and _not_ours(e)]   # yt-dlp and our code: from the packs
a.datas = [e for e in a.datas if _not_youtube(e)]     # (the solver's scripts too)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NiSHPlayer",
    console=False,
    icon="assets/icon.ico",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="NiSHPlayer", upx=False)
