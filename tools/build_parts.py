"""Get the big, rarely changing parts of the app from our own GitHub release 'build-parts':
the AI models (Demucs checkpoints), ffmpeg.exe and deno.exe. Builds never depend on outside servers
and every build bundles the exact same files.

    python tools/build_parts.py           (in the build workflow; needs the gh CLI and GH_TOKEN)

puts  models/checkpoints/*.th, vendor/ffmpeg.exe, vendor/deno.exe

The release holds the files and build-parts.json (name -> size, sha256, where it came from). A file
that isn't there yet is fetched once and, with PARTS_UPLOAD=1, added to the release:
- the AI models: copied from a published NiSH Player download (PARTS_SEED_RELEASE, default v2.0.0) -
  the same files users already have - and checked against the hash in their names; Meta's server is
  only the last resort.
- ffmpeg (BtbN's build with Rubber Band) and Deno: their latest release.
To take a newer ffmpeg or Deno: delete it from the release; the next build fetches and stores the
latest. (That changes the engine: it belongs in a new full download, see BASE.)
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = "build-parts"
MANIFEST = "build-parts.json"
WORK = ROOT / "tmp" / "parts"
MODELS = ("htdemucs_ft", "htdemucs_6s")
FFMPEG = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
DENO = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"


def gh(*args, check=True, capture=True):
    r = subprocess.run(["gh", *args, "--repo", os.environ.get("GITHUB_REPOSITORY", "nish-vibes/nish-player")],
                       capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"gh {' '.join(args)} failed:\n{r.stderr}")
    return r


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_hash_ok(path):
    """Demucs checkpoints are named <signature>-<first hex digits of their sha256>.th"""
    m = re.search(r"-([a-f0-9]+)\.th$", Path(path).name)
    return bool(m) and sha256(path).startswith(m.group(1))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nish-player-build"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def release_assets():
    r = gh("release", "view", RELEASE, "--json", "assets", check=False)
    if r.returncode != 0:
        return None
    return {a["name"] for a in json.loads(r.stdout)["assets"]}


def download_assets(names, dest):
    dest.mkdir(parents=True, exist_ok=True)
    args = ["release", "download", RELEASE, "-D", str(dest), "--clobber"]
    for n in names:
        args += ["-p", n]
    gh(*args)


# ---------- getting a part the first time ----------

def seed_models(dest):
    """The AI models from a published download (the files users already have), else from Meta."""
    seed = os.environ.get("PARTS_SEED_RELEASE", "v2.0.0")
    got = []
    zdir = WORK / "seed"
    r = gh("release", "download", seed, "-p", "NiSHPlayer-windows.zip", "-D", str(zdir), "--clobber", check=False)
    zpath = zdir / "NiSHPlayer-windows.zip"
    if r.returncode == 0 and zpath.is_file():
        with zipfile.ZipFile(zpath) as z:
            for n in z.namelist():
                if re.search(r"/_internal/models/checkpoints/[^/]+\.th$", n):
                    target = dest / Path(n).name
                    with z.open(n) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out, 1 << 20)
                    if not model_hash_ok(target):
                        raise SystemExit(f"{target.name} from {seed} doesn't match the hash in its name")
                    got.append((target.name, f"NiSH Player {seed} download"))
        zpath.unlink()
    if got:
        return got
    print(f"No models in the {seed} download; downloading them from Meta (dl.fbaipublicfiles.com)")
    import torch
    torch.hub.set_dir(str(WORK / "hub"))
    from demucs.pretrained import get_model
    for name in MODELS:
        get_model(name)
    for f in (WORK / "hub" / "checkpoints").glob("*.th"):
        shutil.copy2(f, dest / f.name)
        got.append((f.name, "dl.fbaipublicfiles.com"))
    return got


def seed_exe(name, url, dest):
    data = fetch(url)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        member = next(n for n in z.namelist() if n.endswith("/" + name) or n == name)
        (dest / name).write_bytes(z.read(member))
    return [(name, url)]


def ffmpeg_ok(path):
    try:
        out = subprocess.run([str(path), "-hide_banner", "-filters"], capture_output=True, text=True,
                             timeout=60).stdout
    except Exception:
        return False
    return "rubberband" in out


# ---------- main ----------

def main():
    store = WORK / "store"
    shutil.rmtree(WORK, ignore_errors=True)
    store.mkdir(parents=True)
    assets = release_assets()
    manifest = {"files": {}}
    if assets and MANIFEST in assets:
        download_assets([MANIFEST], store)
        manifest = json.loads((store / MANIFEST).read_text(encoding="utf-8"))
    files = manifest["files"]
    have = [n for n in files if n in (assets or ())]
    if have:
        download_assets(have, store)
    for n in have:
        if sha256(store / n) != files[n]["sha256"]:
            raise SystemExit(f"{n} in the {RELEASE} release doesn't match {MANIFEST}")

    added = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not any(n.endswith(".th") for n in have):
        added += seed_models(store)
    if "ffmpeg.exe" not in have:
        added += seed_exe("ffmpeg.exe", FFMPEG, store)
    if "deno.exe" not in have:
        added += seed_exe("deno.exe", DENO, store)
    for n, source in added:
        files[n] = {"size": (store / n).stat().st_size, "sha256": sha256(store / n), "source": source, "added": stamp}

    if not ffmpeg_ok(store / "ffmpeg.exe"):
        raise SystemExit("This ffmpeg build has no rubberband filter")
    models = sorted(n for n in files if n.endswith(".th"))
    for n in models:
        if not model_hash_ok(store / n):
            raise SystemExit(f"{n} doesn't match the hash in its name")

    if added and os.environ.get("PARTS_UPLOAD") == "1":
        (store / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        if assets is None:
            gh("release", "create", RELEASE, "--prerelease", "--latest=false", "--title", "Build parts",
               "--notes", "Files every NiSH Player build bundles: the AI models (Demucs), ffmpeg and Deno. "
                          "Used by the build workflow; nothing to download here.")
        for n, _ in added:
            gh("release", "upload", RELEASE, str(store / n), "--clobber")
        gh("release", "upload", RELEASE, str(store / MANIFEST), "--clobber")     # last: it lists the files
        print(f"Added to the {RELEASE} release: {', '.join(n for n, _ in added)}")
    elif added:
        print(f"Not stored (PARTS_UPLOAD isn't 1): {', '.join(n for n, _ in added)}")

    (ROOT / "vendor").mkdir(exist_ok=True)
    ck = ROOT / "models" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    for n in ("ffmpeg.exe", "deno.exe"):
        shutil.copy2(store / n, ROOT / "vendor" / n)
    for n in models:
        shutil.copy2(store / n, ck / n)
    for n in sorted(files):
        f = files[n]
        print(f"{n:28} {f['size'] / 1e6:7.1f} MB  {f['sha256'][:12]}  from {f['source']} ({f['added']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
