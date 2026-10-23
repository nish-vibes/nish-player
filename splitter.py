"""Split song: a YouTube link or a file on this computer -> a song folder with the original,
an Auto440 copy, a karaoke MP3 and/or stems (AI separation with Demucs), plus a project file.

Folder layout (suffixes are configurable, added after the name with a space):
    <location>/<Name>/~<Name>.nish                          project (sorts to the top)
    <location>/<Name>/<Name> Original.<ext>                  original, not re-encoded (Opus saved as .opus)
    <location>/<Name>/<Name> Auto440.flac                    the original tuned to A = 440 Hz
    <location>/<Name>/<Name> KARAOKE[ Auto440].mp3           karaoke, always MP3 320
    <location>/<Name>/Separated Stems - <Name>/<Name> VOX[ Auto440].flac ...   4 or 6 stems
YouTube imports always keep the original and its Auto440 copy.
"""
import copy
import json
import os
import re
import shutil
import traceback
import tempfile
from pathlib import Path

import numpy as np

import engine
import tuning

SETTINGS_FILE = engine.DATA_DIR / "split.json"
SIX = ["vocals", "drums", "bass", "guitar", "piano", "other"]
FOUR = ["vocals", "drums", "bass", "other"]
LABELS = {"vocals": "Vocals", "drums": "Drums", "bass": "Bass", "guitar": "Guitar", "piano": "Piano",
          "other": "Other", "karaoke": "Karaoke", "original": "Original", "tuned": "Original 440 Hz"}
OUTPUTS = ["original", "karaoke", "stems", "stems6"]
MODEL_BEST = "htdemucs_ft"     # fine-tuned: the best Demucs model for vocals/drums/bass/other
MODEL_SIX = "htdemucs_6s"      # the only Demucs model with guitar and piano


def _desktop():
    try:
        import settings
        return settings.desktop()
    except Exception:
        return str(Path.home() / "Desktop")


DEFAULTS = {
    "suffixes": {"original": "Original", "tune": "Auto440", "karaoke": "KARAOKE", "vocals": "VOX",
                 "drums": "DRM", "bass": "BASS", "guitar": "GTR", "piano": "KEYS", "other": "MISC"},
    "stems_folder": "Separated Stems - {name}",
    "fmt": "FLAC",              # stems and the Auto440 copy (karaoke is always MP3 320)
    "out_root": "",             # '' = the Desktop
    "out": {"original": True, "karaoke": False, "stems": False, "stems6": True},
    "tune": {"original": True, "karaoke": True, "stems": True},
    "workspace": True,
    "source": "youtube",        # "youtube" (a link) or "file" (a file on this computer)
}
FORMATS = {"FLAC": ".flac", "WAV": ".wav", "MP3": ".mp3", "OPUS": ".opus"}
HEADROOM = 0.891  # -1 dBFS: the loudest output peak is brought down to this (never boosted)


class Cancelled(Exception):
    pass


# ---------- settings ----------

def default_settings():
    return copy.deepcopy(DEFAULTS)


def load_settings():
    s = default_settings()
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return s
    for k, v in saved.items():
        if isinstance(s.get(k), dict) and isinstance(v, dict):
            for sk, sv in v.items():
                if sk in s[k] and isinstance(sv, type(s[k][sk])):
                    s[k][sk] = sv
        elif k in s and isinstance(v, type(s[k])):
            s[k] = v
    if s["fmt"] not in FORMATS:
        s["fmt"] = "FLAC"
    if s["out"]["stems"] and s["out"]["stems6"]:
        s["out"]["stems"] = False
    return s


def location(opts):
    """Where song folders are created (the Desktop unless the user picked another place)."""
    return opts.get("out_root") or _desktop()


def effective(opts, local):
    """(outputs, tune flags) as they will really be used. YouTube always keeps the original;
    the Auto440 copy of the original is made whenever its switch is on (also without the copy, for a
    file); Stems and Stems x6 exclude each other."""
    out = dict(opts["out"])
    tune = dict(opts["tune"])
    if not local:
        out["original"] = True
    if out.get("stems6"):
        out["stems"] = False
    return out, tune


def save_settings(s):
    try:
        SETTINGS_FILE.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---------- names ----------

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name, limit=80):
    s = _BAD.sub("", name or "").strip().rstrip(". ")
    s = re.sub(r"\s+", " ", s)
    return s[:limit].rstrip(". ") or "track"


def _n(name, *parts):
    return " ".join([name] + [p for p in parts if p])


def plan(name, opts, orig_ext=".opus", local=False, tuned=True):
    """What will be written, as [(key, relative path, label)] in display order.

    tuned=False: Auto 440 couldn't be used (no tuning detected), so nothing gets the Auto440 tag."""
    sfx = opts["suffixes"]
    ext = FORMATS.get(opts["fmt"], ".flac")
    out, tune = effective(opts, local)
    T = lambda k: sfx["tune"] if (tuned and tune.get(k)) else ""
    items = []
    if out["original"]:
        items.append(("original", _n(name, sfx["original"]) + orig_ext, "Original"))
    if tuned and tune["original"]:
        items.append(("tuned", _n(name, sfx["tune"]) + ext, LABELS["tuned"]))
    if out["karaoke"]:
        items.append(("karaoke", _n(name, sfx["karaoke"], T("karaoke")) + ".mp3", "Karaoke"))
    keys = SIX if out["stems6"] else FOUR if out["stems"] else []
    if keys:
        folder = sanitize(opts["stems_folder"].replace("{name}", name), limit=100)
        for k in keys:
            items.append((k, f"{folder}/" + _n(name, sfx[k], T("stems")) + ext, LABELS[k]))
    return items


def project_rel(name, opts=None):
    """The project file in the song folder; '~' keeps it at the top of the folder."""
    return f"~{name}.nish"


def model_for(opts, local=False):
    """Which AI runs, or None: always the best one for the choice."""
    out, _ = effective(opts, local)
    if out["stems6"]:
        return MODEL_SIX
    if out["stems"] or out["karaoke"]:
        return MODEL_BEST
    return None


def workspace_keys(opts, local=False):
    """Which of the written files go into the player."""
    out, _ = effective(opts, local)
    if out["stems6"]:
        return SIX
    if out["stems"]:
        return FOUR
    if out["karaoke"]:
        return ["karaoke"]
    return ["tuned", "original"]       # the tuned copy if there is one, else the original


# ---------- YouTube ----------

def is_url(s):
    return bool(re.match(r"^https?://", (s or "").strip(), re.I))


def fetch_info(url):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
            "format": "bestaudio[format_id!*=drc]/bestaudio/best"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        raise RuntimeError("That's a playlist – paste a link to a single video.")
    codec = (info.get("acodec") or "").split(".")[0]
    abr = info.get("abr")
    q = " ".join(x for x in [{"opus": "Opus", "mp4a": "AAC"}.get(codec, codec.upper()),
                             f"{abr:.0f} kbps" if abr else ""] if x)
    return {"title": info.get("title") or "track", "duration": info.get("duration"),
            "id": info.get("id"), "ext": saved_ext(info.get("ext"), codec), "quality": q}


def saved_ext(ext, codec):
    """The extension the original gets in the song folder (see keep_original)."""
    ext = "." + (ext or "opus").lower().lstrip(".")
    return ".opus" if ext in (".webm", ".mka") and codec in ("opus", "") else ext


def download(url, folder, name, on_progress, check_cancel, work=None):
    """Best audio, saved without re-encoding as <folder>/<name>.<ext>.

    YouTube's best audio is usually Opus inside a .webm container; that is copied (not re-encoded)
    into a plain .opus file so it plays everywhere and is easy to recognise. The download goes to
    a temporary folder first and is moved into the song folder when it's complete."""
    import yt_dlp

    for p in folder.glob(glob_escape(name) + ".*"):
        if p.suffix.lower() in engine.AUDIO_EXTS and p.stem == name and p.stat().st_size > 0:
            on_progress(1.0)
            return p  # already downloaded

    def hook(d):
        check_cancel()
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(d.get("downloaded_bytes", 0) / total)

    tmpdir = Path(work or tempfile.mkdtemp(prefix="nish_dl_")) / "download"
    tmpdir.mkdir(parents=True, exist_ok=True)
    opts = {"format": "bestaudio[format_id!*=drc]/bestaudio/best",
            "outtmpl": str(tmpdir / "audio.%(ext)s"), "paths": {"home": str(tmpdir), "temp": str(tmpdir)},
            "noplaylist": True, "quiet": True, "no_warnings": True, "noprogress": True,
            "progress_hooks": [hook], "ffmpeg_location": str(Path(engine.ffmpeg_exe()).parent)}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists() or path.stat().st_size == 0:
        found = [p for p in tmpdir.iterdir() if p.is_file() and p.suffix.lower() in engine.AUDIO_EXTS
                 and p.stat().st_size > 0]
        if not found:
            raise RuntimeError("The download finished but no audio file was produced.")
        path = found[0]
    return keep_original(path, folder, name, (info or {}).get("acodec"))


def keep_original(src, folder, name, acodec=None):
    """Put the downloaded audio in the song folder as <name>.<ext>, without re-encoding.
    Opus in a .webm/.mka container becomes a plain .opus file (a stream copy)."""
    src = Path(src)
    folder.mkdir(parents=True, exist_ok=True)
    codec = (acodec or "").split(".")[0].lower()
    if src.suffix.lower() in (".webm", ".mka") and (codec == "opus" or not codec):
        dst = folder / (name + ".opus")
        tmp = src.with_name("remux.opus")
        try:
            engine._run([engine.ffmpeg_exe(), "-hide_banner", "-y", "-i", str(src), "-vn", "-map", "0:a:0",
                         "-c:a", "copy", "-map_metadata", "0", str(tmp)])
            if tmp.exists() and tmp.stat().st_size > 0:
                shutil.move(str(tmp), str(dst))
                try:
                    src.unlink()
                except OSError:
                    pass
                return dst
        except Exception:
            traceback.print_exc()   # not Opus after all: keep the file as it came
    dst = folder / (name + src.suffix.lower())
    shutil.move(str(src), str(dst))
    return dst


def glob_escape(s):
    return re.sub(r"([\[\]*?])", r"[\1]", s)


# ---------- separation ----------

_MODELS = {}


class _Progress:
    """Stands in for tqdm inside demucs.apply so we get real separation progress."""

    def __init__(self):
        self.cb = self.check_cancel = None
        self.parts, self.done_parts = 1, 0

    def tqdm(self, iterable, **kw):
        items = list(iterable)
        n = max(1, len(items))
        part = self.done_parts
        for i, it in enumerate(items):
            if self.check_cancel:
                self.check_cancel()
            if self.cb:
                self.cb(min(1.0, (part + i / n) / self.parts))
            yield it
        self.done_parts += 1


_PROGRESS = _Progress()


MODELS_DIR = engine.BASE_DIR / "models"   # AI models bundled with the app (models/checkpoints/*.th)


def bundled_models():
    """Names of the model files that came with the app."""
    ck = MODELS_DIR / "checkpoints"
    return sorted(p.name for p in ck.glob("*.th")) if ck.is_dir() else []


def use_bundled_models():
    """Point Demucs at the models that ship with the app, so nothing is downloaded."""
    if bundled_models():
        import torch
        torch.hub.set_dir(str(MODELS_DIR))
        return True
    return False


def demucs_separate(audio, model_name, on_progress, check_cancel):
    """audio (frames, 2) float32 at 44.1 kHz -> {stem name: (frames, 2) array}."""
    os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")
    import torch
    import demucs.apply as dapply
    from demucs.pretrained import get_model

    if model_name not in _MODELS:
        use_bundled_models()
        m = get_model(model_name)
        m.eval()
        _MODELS[model_name] = m
    model = _MODELS[model_name]
    wav = torch.from_numpy(np.ascontiguousarray(audio.T))
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std()
    if not torch.isfinite(std) or std < 1e-8:
        std = torch.tensor(1.0)
    wav = (wav - mean) / std
    use_progress = True
    try:
        _PROGRESS.cb, _PROGRESS.check_cancel = on_progress, check_cancel
        _PROGRESS.parts = len(getattr(model, "models", [None]))
        _PROGRESS.done_parts = 0
        dapply.tqdm = _PROGRESS
    except Exception:
        use_progress = False
    torch.set_num_threads(max(1, os.cpu_count() or 2))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    with torch.no_grad():
        sources = dapply.apply_model(model, wav[None], device=device, shifts=1, split=True,
                                     overlap=0.25, progress=use_progress)[0]
    sources = sources * std + mean
    return {name: sources[i].cpu().numpy().T.astype(np.float32).copy()
            for i, name in enumerate(model.sources)}


# ---------- the whole job ----------

SEPARATOR = None  # tests can swap in a stand-in for the AI


def run(source, name, opts, stage=lambda key, frac: None, check_cancel=lambda: None, separator=None):
    """source: YouTube link or a local file. name: '' = use the video title / file name.

    stage(key, frac) reports progress for 'download', 'split', 'tune', 'save'.
    Returns {"folder", "files": {key: path}, "load": [(path, label)], "tuning": text, "name", "project"}."""
    opts = copy.deepcopy(opts)
    local = os.path.isfile(source)
    out, tune = effective(opts, local)
    if not any(out.values()) and not tune["original"]:
        raise RuntimeError("Choose what to make first.")
    root = Path(location(opts))
    sfx = opts["suffixes"]
    work = Path(tempfile.mkdtemp(prefix="nish_"))
    files = {}
    try:
        # 1. the original
        stage("download", 0.0)
        if local:
            name = sanitize(name or Path(source).stem)
            folder = root / name
            folder.mkdir(parents=True, exist_ok=True)
            src = Path(source)
            if out["original"]:
                orig = folder / (_n(name, sfx["original"]) + src.suffix.lower())
                if src.resolve() != orig.resolve() and not orig.exists():
                    shutil.copy2(src, orig)
                files["original"] = orig
            else:
                orig = src                                   # used for the split, not copied
        else:
            if not name:
                name = fetch_info(source)["title"]
            name = sanitize(name)
            folder = root / name
            folder.mkdir(parents=True, exist_ok=True)
            orig = download(source, folder, _n(name, sfx["original"]), lambda p: stage("download", p),
                            check_cancel, work=work)
            files["original"] = orig
        if not orig.exists() or orig.stat().st_size == 0:
            raise RuntimeError("The original audio couldn't be saved in the song folder.")
        stage("download", 1.0)
        check_cancel()

        model = model_for(opts, local)
        want_tune = tune["original"] or any(tune.get(k) for k, on in out.items() if on and k in ("karaoke", "stems")) \
            or (out["stems6"] and tune.get("stems"))
        need_audio = model or tune["original"]
        audio = engine.decode(orig) if need_audio else None

        # 2. AI split (one run: the best model for the choice)
        sep = {}
        if model:
            stage("split", 0.0)
            sep = (separator or SEPARATOR or demucs_separate)(audio, model, lambda p: stage("split", p), check_cancel)
            stage("split", 1.0)
            check_cancel()
        outputs = {}
        keys = SIX if out["stems6"] else FOUR if out["stems"] else []
        for k in keys:
            outputs[k] = sep.get(k, np.zeros_like(audio))
        if out["karaoke"]:
            outputs["karaoke"] = sum(v for k, v in sep.items() if k != "vocals")
        if tune["original"]:
            outputs["tuned"] = audio

        # 3. Auto 440 (measured on the tonal parts when we have them)
        tuning_text = ""
        tuned = False
        group = lambda k: "original" if k == "tuned" else "karaoke" if k == "karaoke" else "stems"
        if want_tune and outputs:
            stage("tune", 0.0)
            tonal = [v for k, v in sep.items() if k != "drums"] or [audio]
            mono = sum(v.mean(axis=1) for v in tonal)
            offset, conf = tuning.estimate_offset_cents(mono, engine.SR)
            corr = tuning.correction_cents(offset, conf)
            detected = offset is not None and conf >= 0.12
            if corr:
                tuned = True
                tuning_text = f"Recording measured {offset:+.0f} cents from A440, corrected by {corr:+.0f}."
                todo = [k for k in outputs if tune.get(group(k))]
                for i, k in enumerate(todo):
                    check_cancel()
                    outputs[k] = engine.render(outputs[k], 1.0, 0, cents=corr)   # varispeed
                    stage("tune", (i + 1) / len(todo))
            elif detected:
                tuned = True
                tuning_text = "Already at A440."
            else:
                tuning_text = "Couldn't detect the tuning clearly, so nothing was tuned."
            stage("tune", 1.0)
        if not tuned:
            outputs.pop("tuned", None)        # no Auto440 copy when the tuning couldn't be found

        # 4. save (one shared gain for headroom, so the stems still add up to the song)
        items = plan(name, opts, orig.suffix.lower(), local=local, tuned=tuned)
        rel = {k: r for k, r, _ in items}
        labels = {k: lbl for k, _, lbl in items}
        stage("save", 0.0)
        peak = max((float(np.abs(v).max()) for v in outputs.values() if v.size), default=0.0)
        gain = min(1.0, HEADROOM / peak) if peak > HEADROOM else 1.0
        for i, k in enumerate(outputs):
            check_cancel()
            dst = folder / rel[k]
            dst.parent.mkdir(parents=True, exist_ok=True)
            engine._encode(outputs[k] * gain, dst, "MP3" if k == "karaoke" else opts["fmt"])
            files[k] = dst
            stage("save", (i + 1) / len(outputs))
        stage("save", 1.0)
        load = []
        for k in workspace_keys(opts, local):
            if k in files:
                load.append((files[k], labels.get(k, name)))
                if k == "tuned":
                    break                         # the tuned copy instead of the original
        proj = None
        if load:
            import project
            try:   # a project in the song folder, so the song can be opened again later
                proj = project.save(folder / project_rel(name), project.new_state(load))
            except Exception:
                traceback.print_exc()
                proj = None
        return {"folder": folder, "files": files, "load": load, "tuning": tuning_text, "name": name,
                "project": proj}
    finally:
        shutil.rmtree(work, ignore_errors=True)
