# PyInstaller build recipe. Run on Windows:  pyinstaller NiSHPlayer.spec
# Expects ffmpeg.exe in vendor/ (the GitHub workflow downloads it).
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], ["smoketest"]
for pkg in ("customtkinter", "darkdetect", "tkinterdnd2", "sounddevice", "_sounddevice_data"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

if Path("vendor", "ffmpeg.exe").exists():
    binaries.append((str(Path("vendor", "ffmpeg.exe")), "bin"))
datas.append(("assets", "assets"))

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "IPython", "jupyter", "notebook", "pytest", "scipy", "pandas"],
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
