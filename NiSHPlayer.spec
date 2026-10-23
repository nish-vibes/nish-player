# PyInstaller build recipe. Run on Windows:  pyinstaller NiSHPlayer.spec
# Expects ffmpeg.exe and deno.exe in vendor/ (the GitHub workflow downloads them).
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], ["smoketest", "youtube_ui", "splitter", "theme",
                                                  "settings", "settings_menu", "updater", "project", "project_ui",
                                                  "instance", "split_choices",
                                                  "lane", "widgets", "layout", "tracks", "speed_pitch", "export_dialog"]
# AI separation (Demucs) and YouTube (yt-dlp + its JS challenge solver)
datas += collect_data_files("demucs")
hiddenimports += collect_submodules("demucs")
# Some Demucs checkpoints were pickled with numpy 1.x paths (numpy.core.*)
hiddenimports += collect_submodules("numpy.core")
for pkg in ("customtkinter", "darkdetect", "tkinterdnd2", "sounddevice", "_sounddevice_data",
            "yt_dlp_ejs", "soundfile", "_soundfile_data"):
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
