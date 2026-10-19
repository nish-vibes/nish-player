"""Manual updates from the GitHub releases page.

check()     -> asks GitHub for the latest release
download()  -> downloads its zip; unpack() puts it in a folder next to the app ("<app>.new")
               (the menu then says it's ready; nothing is installed until the user says so)
install()   -> starts a small PowerShell helper that waits for the app to close, swaps the folders
               (keeping the old one until the new one is in place, and putting it back if anything
               fails), starts the new version and removes the old one.

User settings live in %LOCALAPPDATA%\\NiSH Player, outside the app folder, so they are never touched.
"""
import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "nish-vibes/nish-player"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET = "NiSHPlayer-windows.zip"
EXE = "NiSHPlayer.exe"
UA = {"User-Agent": "NiSH-Player-updater", "Accept": "application/vnd.github+json"}


def app_dir():
    """The folder holding NiSHPlayer.exe (None when running from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def current_tag():
    """Release tag of this build, e.g. 'v1.3.0' or 'v1.3.0-yt2026.10.10'."""
    for base in filter(None, (app_dir(), Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", None)
                              else None, Path(__file__).resolve().parent)):
        f = base / "build_tag.txt"
        if f.is_file():
            t = f.read_text(encoding="utf-8").strip()
            if t:
                return t
    for base in filter(None, (Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", None) else None,
                              Path(__file__).resolve().parent)):
        f = base / "VERSION"
        if f.is_file():
            return "v" + f.read_text(encoding="utf-8").strip()
    return "v0"


def version_text(tag=None):
    """'1.3.0' (with ' · YouTube fix 2026.10.10' for weekly builds)."""
    tag = (tag or current_tag()).lstrip("v")
    if "-yt" in tag:
        v, yt = tag.split("-yt", 1)
        return f"{v} · YouTube fix {yt}"
    return tag


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url, timeout=20):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=_ctx())


def check():
    """{'tag', 'newer', 'url', 'size', 'notes'} for the latest release. Raises on network errors."""
    with _open(API) as r:
        rel = json.loads(r.read().decode("utf-8"))
    asset = next((a for a in rel.get("assets", []) if a.get("name") == ASSET), None)
    tag = rel.get("tag_name", "")
    return {"tag": tag, "newer": bool(tag) and tag != current_tag(), "url": asset and asset["browser_download_url"],
            "size": asset and asset.get("size"), "notes": rel.get("body", "")}


def can_update():
    """Self-update needs the frozen app in a folder whose parent we can write to."""
    d = app_dir()
    if d is None or os.name != "nt":
        return False
    probe = d.parent / f".{d.name}.write-test"
    try:
        probe.mkdir(exist_ok=True)
        probe.rmdir()
        return True
    except OSError:
        return False


def staging_dir(target=None):
    target = Path(target or app_dir())
    return target.parent / (target.name + ".new")


def download(url, dest_zip, progress=lambda f: None, cancelled=lambda: False):
    dest_zip = Path(dest_zip)
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    part = dest_zip.with_suffix(".part")
    with _open(url, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancelled():
                raise RuntimeError("Cancelled.")
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                progress(done / total)
    os.replace(part, dest_zip)
    return dest_zip


def unpack(zip_path, target=None):
    """Unpack the release zip into '<app>.new' next to the app. Returns that folder."""
    stage = staging_dir(target)
    shutil.rmtree(stage, ignore_errors=True)
    tmp = stage.parent / (stage.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp)
    exe = next(tmp.rglob(EXE), None)
    if exe is None:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("The downloaded update doesn't contain NiSH Player.")
    os.replace(exe.parent, stage)
    shutil.rmtree(tmp, ignore_errors=True)
    return stage


def staged_update():
    """(folder, tag) of an update that was downloaded but not installed yet, else None."""
    d = app_dir()
    if d is None:
        return None
    stage = staging_dir(d)
    tag_file = stage / "build_tag.txt"
    try:
        if (stage / EXE).is_file() and tag_file.is_file():
            tag = tag_file.read_text(encoding="utf-8").strip()
            if tag and tag != current_tag():
                return stage, tag
    except OSError:
        pass
    return None


SCRIPT = r'''$ErrorActionPreference = "Stop"
$target = '{target}'
$stage  = '{stage}'
$old    = '{old}'
$log    = '{log}'
function Log($m) {{ Add-Content -LiteralPath $log -Value ("[" + (Get-Date -Format s) + "] " + $m) }}
try {{ Wait-Process -Id {pid} -Timeout 120 -ErrorAction SilentlyContinue }} catch {{}}
Start-Sleep -Milliseconds 500
$ok = $false
for ($i = 0; $i -lt 20 -and -not $ok; $i++) {{
  try {{
    if (Test-Path -LiteralPath $old) {{ Remove-Item -LiteralPath $old -Recurse -Force }}
    Move-Item -LiteralPath $target -Destination $old
    $ok = $true
  }} catch {{ Start-Sleep -Milliseconds 500 }}
}}
if (-not $ok) {{
  Log "Couldn't move the old version out of the way; update not installed."
}} else {{
  try {{
    Move-Item -LiteralPath $stage -Destination $target
    Log "Updated."
    Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue
  }} catch {{
    Log ("Update failed, restoring the old version: " + $_)
    Move-Item -LiteralPath $old -Destination $target
  }}
}}
if ({restart}) {{ Start-Process -FilePath (Join-Path $target '{exe}') }}
'''


def _ps_quote(p):
    return str(p).replace("'", "''")


def write_script(target, stage, pid, restart=True, log=None):
    target, stage = Path(target), Path(stage)
    old = target.parent / (target.name + ".old")
    log = Path(log or (target.parent / (target.name + ".update.log")))
    text = SCRIPT.format(target=_ps_quote(target), stage=_ps_quote(stage), old=_ps_quote(old),
                         log=_ps_quote(log), pid=int(pid), restart="$true" if restart else "$false", exe=EXE)
    script = stage.parent / (target.name + ".update.ps1")
    script.write_text(text, encoding="utf-8-sig")   # BOM: PowerShell reads non-ASCII paths correctly
    return script


def run_script(script, wait=False):
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
           "-File", str(script)]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, "DETACHED_PROCESS", 0)
    p = subprocess.Popen(cmd, creationflags=flags, close_fds=True, cwd=str(Path(script).parent))
    if wait:
        p.wait()
    return p


def install(stage, restart=True):
    """Start the helper; the caller must then quit the app."""
    script = write_script(app_dir(), stage, os.getpid(), restart)
    run_script(script)
