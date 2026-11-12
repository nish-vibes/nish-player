"""Make the app update (see apppack.py): our code plus the YouTube pack, as one small download.

    python tools/build_app_pack.py <out>      (after tools/build_youtube_pack.py <out>)

reads  VERSION (the app's version), BASE (the full download it is made for), <out>/youtube (the YouTube pack)
writes
    <out>/app/                                 our code as a folder (built into the app: _internal/nish_app)
    <out>/app-update-<version>-yt<yt>.zip       app/ + youtube/, to publish
    <out>/app-update.json                       its description (version, youtube, base, size, sha256)
"""
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import apppack  # noqa: E402
import ytpack  # noqa: E402


def app_files():
    """Every top-level .py is part of the app (start.py too: apppack reads its rules)."""
    return sorted(ROOT.glob("*.py"))


def build(out):
    out = Path(out)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    base = (ROOT / "BASE").read_text(encoding="utf-8").strip()
    yt = ytpack.read_info(out / "youtube")
    if not yt:
        raise SystemExit(f"no YouTube pack in {out / 'youtube'} (run tools/build_youtube_pack.py {out} first)")
    app = out / "app"
    shutil.rmtree(app, ignore_errors=True)
    app.mkdir(parents=True)
    for f in app_files():
        shutil.copy2(f, app / f.name)
    shutil.copy2(ROOT / "VERSION", app / "VERSION")
    info = {"format": apppack.FORMAT, "version": version, "base": base,
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    (app / "pack.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    if not apppack.read_info(app):
        raise SystemExit("the app folder isn't readable as an app")

    asset = f"app-update-{version}-yt{yt['version']}.zip"
    zpath = out / asset
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for top in ("app", "youtube"):
            for f in sorted(p for p in (out / top).rglob("*") if p.is_file() and "__pycache__" not in p.parts):
                zi = zipfile.ZipInfo(f.relative_to(out).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, f.read_bytes())
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    manifest = {"format": apppack.FORMAT, "version": version, "youtube": yt["version"], "base": base,
                "asset": asset, "size": zpath.stat().st_size, "sha256": sha, "built": info["built"]}
    (out / apppack.MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"App update: {version} for base {base}, YouTube {yt['version']}, {zpath.stat().st_size / 1e6:.1f} MB")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    build(sys.argv[1])
