"""YouTube pack tests: choosing the pack to use, falling back from a broken one, installing.

Run:  python tests/test_ytpack.py
(With yt-dlp and yt-dlp-ejs installed, it also builds a real pack and checks it in a new process.)
"""
import hashlib
import importlib.util
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402
import ytpack  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="nish-ytpack-"))
engine.DATA_DIR = TMP / "data"
BUNDLED = TMP / "app" / "youtube"
ytpack.bundled_dir = lambda: BUNDLED


def ok(msg):
    print("ok:", msg)


def fake_pack(folder, version, min_app="2.0.0", broken=False):
    """A tiny stand-in for yt-dlp + yt-dlp-ejs that reports its version."""
    folder = Path(folder)
    (folder / "yt_dlp").mkdir(parents=True, exist_ok=True)
    (folder / "yt_dlp_ejs").mkdir(parents=True, exist_ok=True)
    code = "raise ImportError('broken pack')\n" if broken else f"PACK = {version!r}\n"
    (folder / "yt_dlp" / "__init__.py").write_text(code, encoding="utf-8")
    (folder / "yt_dlp_ejs" / "__init__.py").write_text("version = '0.8.0'\n", encoding="utf-8")
    (folder / "pack.json").write_text(json.dumps({"format": 1, "version": version, "ejs": "0.8.0",
                                                  "min_app": min_app}), encoding="utf-8")
    return folder


def zip_pack(folder, zpath, evil=False):
    with zipfile.ZipFile(zpath, "w") as z:
        for f in sorted(p for p in Path(folder).rglob("*") if p.is_file()):
            z.write(f, f.relative_to(folder).as_posix())
        if evil:
            z.writestr("../../outside.txt", "nope")
    return {"format": 1, "version": json.loads((Path(folder) / "pack.json").read_text())["version"],
            "asset": zpath.name, "url": zpath.resolve().as_uri(), "size": zpath.stat().st_size,
            "sha256": hashlib.sha256(zpath.read_bytes()).hexdigest()}


def main():
    root = ytpack.user_root()

    # --- which pack is used ---
    fake_pack(BUNDLED, "2026.10.26")
    assert ytpack.version() == "2026.10.26"
    with ytpack.use() as yt:
        assert yt.PACK == "2026.10.26"
    fake_pack(root / "2026.11.02", "2026.11.02")
    fake_pack(root / "2026.11.09", "2026.11.09", min_app="9.0.0")      # needs a newer app: ignored
    fake_pack(root / "2026.11.16", "2026.11.16")
    (root / "2026.11.16" / "bad").write_text("x")                        # marked bad: ignored
    (root / "2026.11.20").mkdir()                                        # incomplete: ignored
    assert [i["version"] for _, i in ytpack.packs()] == ["2026.11.02", "2026.10.26"]
    with ytpack.use() as yt:
        assert yt.PACK == "2026.11.02"                                   # switched to the newer one
        fake_pack(root / "2026.11.23", "2026.11.23")
        with ytpack.use() as yt2:
            assert yt2.PACK == "2026.11.02"                              # no switch while in use
    with ytpack.use() as yt:
        assert yt.PACK == "2026.11.23"                                   # switched once nothing ran
    ok("the newest usable pack wins (not a bad, incomplete or too-new one); no switch while in use")

    fake_pack(root / "2026.11.30", "2026.11.30", broken=True)
    with ytpack.use() as yt:
        assert yt.PACK == "2026.11.23"                                   # fell back
    assert (root / "2026.11.30" / "bad").is_file() and ytpack.version() == "2026.11.23"
    ok("a pack that doesn't load is marked bad and the one before it is used")

    # --- installing ---
    src = fake_pack(TMP / "src" / "2026.12.07", "2026.12.07")
    m = zip_pack(src, TMP / "youtube-pack-2026.12.07.zip")
    calls = []
    folder = ytpack.install(m, check=lambda f: (calls.append(f) or True, "ok 2026.12.07"))
    assert folder == root / "2026.12.07" and calls and ytpack.version() == "2026.12.07"
    assert not any(p.name.startswith(".") or p.suffix in (".zip", ".part") for p in root.iterdir())
    with ytpack.use() as yt:
        assert yt.PACK == "2026.12.07"
    ytpack.prune()
    assert sorted(p.name for p in root.iterdir()) == ["2026.12.07"], sorted(p.name for p in root.iterdir())
    ok("install: download, sha256 check, unpack, check in a new process, used next; old packs removed")

    bad = dict(m, sha256="0" * 64)
    try:
        ytpack.install(bad, check=lambda f: (True, ""))
        raise AssertionError("damaged download accepted")
    except RuntimeError as e:
        assert "damaged" in str(e)
    src2 = fake_pack(TMP / "src" / "2026.12.14", "2026.12.14")
    evil = zip_pack(src2, TMP / "youtube-pack-2026.12.14.zip", evil=True)
    try:
        ytpack.install(evil, check=lambda f: (True, ""))
        raise AssertionError("zip with an outside path accepted")
    except RuntimeError as e:
        assert "unexpected file path" in str(e)
    assert not (TMP / "outside.txt").exists() and not (root.parent / "outside.txt").exists()
    good = zip_pack(src2, TMP / "youtube-pack-2026.12.14b.zip")
    try:
        ytpack.install(good, check=lambda f: (False, "FAILED: no module named foo"))
        raise AssertionError("pack that failed its check accepted")
    except RuntimeError as e:
        assert "doesn't work with your version" in str(e)
    assert sorted(p.name for p in root.iterdir()) == ["2026.12.07"] and ytpack.version() == "2026.12.07"
    ok("install refuses a damaged download, a zip pointing outside its folder and a pack that fails its check")

    # --- what GitHub says ---
    man = TMP / "youtube-pack.json"
    man.write_text(json.dumps({**m, "version": "2027.01.04", "min_app": "2.0.0"}), encoding="utf-8")
    ytpack.manifest_url = lambda: man.resolve().as_uri()
    r = ytpack.check()
    assert r["newer"] and not r["needs_app_update"] and r["url"].endswith("/youtube-pack/youtube-pack-2026.12.07.zip")
    man.write_text(json.dumps({**m, "version": "2026.12.07"}), encoding="utf-8")
    assert not ytpack.check()["newer"]
    man.write_text(json.dumps({**m, "version": "2027.01.04", "min_app": "9.0.0"}), encoding="utf-8")
    r = ytpack.check()
    assert not r["newer"] and r["needs_app_update"]
    man.write_text(json.dumps({**m, "asset": "../evil.exe"}), encoding="utf-8")
    try:
        ytpack.check()
        raise AssertionError("odd asset name accepted")
    except RuntimeError:
        pass
    ok("check: newer, same, made for a newer app, odd file name refused")

    # --- a real pack, if yt-dlp is installed ---
    ytpack._unload()                     # forget the stand-ins
    if importlib.util.find_spec("yt_dlp") and importlib.util.find_spec("yt_dlp_ejs"):
        sys.path.insert(0, str(ROOT / "tools"))
        import build_youtube_pack
        man = build_youtube_pack.build(TMP / "real")
        good, details = ytpack.check_in_new_process(TMP / "real" / "youtube")
        assert good, details
        ok(f"a real pack (yt-dlp {man['version']}, {man['size'] / 1e6:.1f} MB) loads in a new process: "
           f"{details.strip()}")
    else:
        print("skipped: real pack (yt-dlp isn't installed here)")
    print("YTPACK TESTS PASSED")


if __name__ == "__main__":
    main()
