"""Make the YouTube pack (see ytpack.py) from the yt-dlp installed in this Python.

    python tools/build_youtube_pack.py <out>

writes
    <out>/youtube/                     the pack as a folder (built into the app: _internal/youtube)
    <out>/youtube-pack-<version>.zip   the pack to publish
    <out>/youtube-pack.json            its description (version, file name, size, sha256, min_app)
"""
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ytpack  # noqa: E402

# The oldest app that can use packs of this format (it loads packs and bundles what yt-dlp relies on).
# Raise it when yt-dlp starts needing something the app doesn't bundle yet.
MIN_APP = "2.0.0"
SKIP_DIRS = {"__pycache__", "__pyinstaller"}


def package_dir(name):
    spec = importlib.util.find_spec(name)
    if not spec or not spec.submodule_search_locations:
        raise SystemExit(f"{name} isn't installed in this Python")
    return Path(list(spec.submodule_search_locations)[0])


def file_version(path):
    """The version a package's version file states (read, not imported)."""
    # "__version__ = '1.2'", "version = '1.2'" or (generated) "__version__ = version = '1.2'"
    m = re.search(r"""^_*version_*\b[^\n]*?=\s*['"]([^'"]+)['"]""", path.read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit(f"no version in {path}")
    return m.group(1)


def build(out):
    out = Path(out)
    folder = out / "youtube"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for name in ytpack.PACKAGES:
        shutil.copytree(package_dir(name), folder / name,
                        ignore=lambda d, names: [n for n in names if n in SKIP_DIRS or n.endswith((".pyc", ".pyo"))])
    version = file_version(folder / "yt_dlp" / "version.py")
    info = {"format": ytpack.FORMAT, "version": version, "ejs": file_version(folder / "yt_dlp_ejs" / "_version.py"),
            "min_app": MIN_APP,
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    (folder / "pack.json").write_text(json.dumps(info, indent=1), encoding="utf-8")

    asset = f"youtube-pack-{version}.zip"
    zpath = out / asset
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(p for p in folder.rglob("*") if p.is_file()):
            zi = zipfile.ZipInfo(f.relative_to(folder).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, f.read_bytes())
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    manifest = {**info, "asset": asset, "size": zpath.stat().st_size, "sha256": sha}
    (out / ytpack.MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"YouTube pack: yt-dlp {version}, yt-dlp-ejs {info['ejs']}, {zpath.stat().st_size / 1e6:.1f} MB")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    build(sys.argv[1])
