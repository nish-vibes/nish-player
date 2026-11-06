# PyInstaller build recipe. Run on Windows:  pyinstaller NiSHPlayer.spec
# Expects ffmpeg.exe and deno.exe in vendor/ (the GitHub workflow downloads them).
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], ["smoketest", "split_ui", "splitter", "theme",
                                                  "settings", "settings_menu", "updater", "project", "project_ui",
                                                  "instance", "split_choices",
                                                  "lane", "widgets", "layout", "tracks", "speed_pitch", "export_dialog",
                                                  "ytpack"]
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

a = Analysis(
    ["app.py"],
    pathex=[],
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


a.pure = [e for e in a.pure if _not_youtube(e)]       # yt-dlp comes from the pack, not the exe
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
