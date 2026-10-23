"""NiSH Player engine: decoding, live mixing, speed/pitch rendering, Auto 440 and export.

ffmpeg decodes every format and does the pitch/speed work (Rubber Band, high quality).
sounddevice plays the live mix. No GUI code in here.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

import tuning

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
BIN_DIR = BASE_DIR / "bin"
if BIN_DIR.is_dir():
    os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

APP_NAME = "NiSH Player"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)
LABELS_FILE = DATA_DIR / "labels.json"

SR = 44100
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
AUDIO_EXTS = {".wav", ".flac", ".mp3", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".aif", ".aiff",
              ".wma", ".mp4", ".webm", ".mka"}
LIMIT = 0.966  # -0.3 dBFS: ceiling for the safety limiter (live and export)
EXPORT_LIMITER = "alimiter=limit=0.966:attack=5:release=80:level=0:latency=1"

try:
    import sounddevice as sd
    SD_ERROR = None
except Exception as e:  # PortAudio missing
    sd = None
    SD_ERROR = str(e)


# ---------- ffmpeg helpers ----------

def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg was not found.")
    return exe


def _run(cmd, input_bytes=None):
    r = subprocess.run(cmd, input=input_bytes, capture_output=True, creationflags=_NO_WINDOW)
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-12:]
        raise RuntimeError("ffmpeg failed:\n" + "\n".join(err))
    return r.stdout


_RUBBERBAND = None


def has_rubberband():
    global _RUBBERBAND
    if _RUBBERBAND is None:
        try:
            out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-filters"], capture_output=True,
                                 text=True, creationflags=_NO_WINDOW).stdout
            _RUBBERBAND = bool(re.search(r"\brubberband\b", out))
        except Exception:
            _RUBBERBAND = False
    return _RUBBERBAND


def decode(path):
    """Any audio file -> float32 array (frames, 2) at 44.1 kHz."""
    base = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
            "-vn", "-ac", "2"]
    tail = ["-f", "f32le", "-acodec", "pcm_f32le", "-"]
    try:
        raw = _run(base + ["-af", f"aresample={SR}:resampler=soxr:precision=28", "-ar", str(SR)] + tail)
    except RuntimeError:
        raw = _run(base + ["-ar", str(SR)] + tail)
    data = np.frombuffer(raw, dtype=np.float32)
    if data.size < 2:
        raise RuntimeError(f"No audio found in {Path(path).name}")
    return data[: data.size // 2 * 2].reshape(-1, 2).copy()


def atempo_chain(t):
    parts = []
    while t > 2.0:
        parts.append(2.0)
        t /= 2.0
    while t < 0.5:
        parts.append(0.5)
        t /= 0.5
    parts.append(t)
    return [f"atempo={p:.6f}" for p in parts]


def vari_ratio(cents):
    """Varispeed (fine-tuning) ratio: pitch and tempo move together, like a turntable."""
    return 2 ** (float(cents) / 1200.0)


def chain_rate(speed, cents=0.0):
    """Original samples per output sample for Rubber Band speed + varispeed fine-tuning."""
    return float(speed) * vari_ratio(cents)


def varispeed_filter(semitones):
    ratio = 2 ** (float(semitones) / 12)
    return f"asetrate={SR * ratio:.4f},aresample={SR}:resampler=soxr:precision=28"


def stretch_filter(speed, semitones, vocal=False, cents=0.0):
    """ffmpeg filter chain. None = unchanged.

    speed/semitones go through Rubber Band (always one pass); fine-tuning (cents) is
    always varispeed, with no tempo compensation. Lowering: varispeed first, so Rubber
    Band's output is never slowed down afterwards. Raising: Rubber Band first, then varispeed.
    """
    rb = _rb_filter(speed, semitones, vocal)
    cents = float(cents)
    vs = varispeed_filter(cents / 100.0) if abs(cents) > 1e-6 else None
    chain = [vs, rb] if cents < 0 else [rb, vs]
    chain = [f for f in chain if f]
    return ",".join(chain) if chain else None


def _rb_filter(speed, semitones, vocal=False):
    speed, semitones = float(speed), float(semitones)
    if abs(speed - 1.0) < 1e-6 and abs(semitones) < 1e-4:
        return None
    ratio = 2 ** (semitones / 12)
    if has_rubberband():
        opts = [f"tempo={speed:.6f}", f"pitch={ratio:.6f}", "pitchq=quality",
                "channels=together", "transients=mixed"]
        if vocal:
            opts.append("formant=preserved")
        return "rubberband=" + ":".join(opts)
    chain = [f"asetrate={SR * ratio:.3f}", f"aresample={SR}:resampler=soxr:precision=28"]
    return ",".join(chain + atempo_chain(speed / ratio))


def render(audio, speed, semitones, vocal=False, cents=0.0):
    """Speed/pitch/fine-tune a decoded (frames, 2) array. Returns a new array."""
    filt = stretch_filter(speed, semitones, vocal, cents)
    if filt is None:
        return audio
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(SR),
           "-ac", "2", "-i", "-", "-af", filt, "-f", "f32le", "-acodec", "pcm_f32le", "-ar", str(SR), "-"]
    raw = _run(cmd, np.ascontiguousarray(audio, dtype=np.float32).tobytes())
    out = np.frombuffer(raw, dtype=np.float32)
    return out[: out.size // 2 * 2].reshape(-1, 2).copy()


def peaks(audio, buckets=1600):
    """Waveform overview: peak level per bucket, 0..1."""
    mono = np.abs(audio).max(axis=1)
    n = len(mono)
    if n == 0:
        return np.zeros(buckets, np.float32)
    edges = np.linspace(0, n, buckets + 1).astype(np.int64)
    edges[-1] = n
    out = np.maximum.reduceat(mono, np.minimum(edges[:-1], n - 1))
    top = float(out.max()) or 1.0
    return (out / top).astype(np.float32)


# ---------- names ----------

STEM_NAMES = {
    "VOX": "Vocals", "VOCALS": "Vocals", "VOCAL": "Vocals", "DRM": "Drums", "DRUMS": "Drums",
    "BASS": "Bass", "GTR": "Guitar", "GUITAR": "Guitar", "PNO": "Piano", "PIANO": "Piano",
    "OTH": "Other", "OTHER": "Other", "KEYS": "Piano", "MISC": "Other", "KAR": "Karaoke", "KARAOKE": "Karaoke",
    "INST": "Instrumental", "INSTRUMENTAL": "Instrumental", "NOVOX": "Karaoke",
}


def guess_label(path):
    stem = Path(path).stem
    tokens = [t for t in re.split(r"[_\-\s.]+", stem) if t]
    if len(tokens) > 1 and tokens[-1].upper() in STEM_NAMES:  # "Song_VOX" style suffix
        return STEM_NAMES[tokens[-1].upper()]
    return stem


def is_vocal(path, label=""):
    s = (Path(path).stem + " " + label).upper()
    return bool(re.search(r"(^|[_\-\s])(VOX|VOCALS?)($|[_\-\s])", s))


def song_name(paths):
    """Common name for a set of files: 'My Song_VOX.wav' + 'My Song_DRM.wav' -> 'My Song'."""
    stems = [Path(p).stem for p in paths]
    if not stems:
        return ""
    if len(stems) == 1:
        return stems[0]
    prefix = os.path.commonprefix(stems)
    prefix = re.sub(r"[_\-\s.(\[]+$", "", prefix)
    return prefix or stems[0]


def load_labels():
    try:
        return json.loads(LABELS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_label(path, label):
    labels = load_labels()
    key = str(Path(path).resolve())
    if label and label != guess_label(path):
        labels[key] = label
    else:
        labels.pop(key, None)
    try:
        LABELS_FILE.write_text(json.dumps(labels, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def fmt_semitones(st):
    return ("+" if st > 0 else "-" if st < 0 else "") + f"{abs(st):g}"


def region_tag(a, b, speed=1.0):
    """'_0m42-1m13' for a loop area (times as heard at this speed)."""
    def mmss(x):
        sec = int(x / SR / speed)
        return f"{sec // 60}m{sec % 60:02d}"
    return f"_{mmss(a)}-{mmss(b)}"


def tags(speed, semis, cents, auto440):
    t = []
    if abs(speed - 1) > 1e-6:
        t.append(f"{speed:.2f}".rstrip("0").rstrip(".") + "x")
    if semis:
        t.append(fmt_semitones(semis) + "semitones")
    if auto440:
        t.append("440hz")
    elif abs(cents) >= 0.5:
        t.append(fmt_semitones(round(cents)) + "ct")
    return t


def safe_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "export"


# ---------- tracks and live mixing ----------

class Track:
    _ids = 0

    def __init__(self, path, audio, label=None):
        Track._ids += 1
        self.id = Track._ids
        self.path = str(path)
        self.orig = audio
        self.label = label or guess_label(path)
        self.peaks = peaks(audio)
        self.volume = 1.0  # linear
        self.mute = False
        self.solo = False
        self.buf = audio       # what is playing (rendered or original)
        self.buf_key = (1.0, 0.0, 0.0)
        self.auto_on = False   # volume automation: when on, the line sets the volume
        self.auto_pts = []     # [(seconds on the song timeline, linear gain 0..1)], sorted
        self._env = None       # (sample positions, gains) for the audio thread, or None

    def set_automation(self, on, pts=None):
        """Turn volume automation on/off and/or replace its points. Off keeps the points."""
        if pts is not None:
            clean = sorted((max(0.0, float(t)), max(0.0, min(1.0, float(v)))) for t, v in pts)
            self.auto_pts = clean
        self.auto_on = bool(on)
        if self.auto_on and self.auto_pts:
            ts = np.array([t for t, _ in self.auto_pts], np.float64) * SR
            vs = np.array([v for _, v in self.auto_pts], np.float32)
            self._env = (ts, vs)
        else:
            self._env = None

    def automation_active(self):
        return self._env is not None

    def envelope(self, pos):
        """Gains at these source sample positions, or None when automation is off."""
        e = self._env
        if e is None:
            return None
        return np.interp(pos, e[0], e[1]).astype(np.float32)

    def level_at(self, seconds):
        """The automation level at a time (seconds on the song timeline)."""
        if not self.auto_pts:
            return self.volume
        ts = [t for t, _ in self.auto_pts]
        vs = [v for _, v in self.auto_pts]
        return float(np.interp(seconds, ts, vs))

    @property
    def vocal(self):
        return is_vocal(self.path, self.label)


LOOP_FADE = 1.0  # default seconds of fade in/out at the edges of a loop area (0–2 s)


def loop_fade_len(a, b, fade=LOOP_FADE):
    """Fade length in samples: `fade` seconds, at most a quarter of the area."""
    return max(0.0, min(fade * SR, (b - a) / 4))


def region_gain(p, a, b, fade=LOOP_FADE):
    """Gain for source positions p inside the loop area a..b (fades at both ends, 0 outside)."""
    f = loop_fade_len(a, b, fade)
    if f < 1:
        g = ((p >= a) & (p < b)).astype(np.float32)
    else:
        g = np.clip((p - a) / f, 0.0, 1.0) * np.clip((b - p) / f, 0.0, 1.0)
    return g.astype(np.float32)


def render_part(audio, a, b, speed, semitones, vocal=False, cents=0.0):
    """Process only source samples a..b (with a little context on both sides)."""
    a, b = int(a), int(b)
    pad = SR
    s0, e0 = max(0, a - pad), min(len(audio), b + pad)
    r = render(audio[s0:e0], speed, semitones, vocal, cents)
    rate = chain_rate(speed, cents)
    off, n = int(round((a - s0) / rate)), int(round((b - a) / rate))
    seg = r[off:off + n]
    if len(seg) < n:
        seg = np.vstack([seg, np.zeros((n - len(seg), 2), np.float32)])
    return seg


class LiveStretcher:
    """Real-time speed + pitch for instant feedback while a slider moves.

    WSOLA time-stretching (overlap-add of windowed grains, each one nudged to line up
    with the previous one) followed by a resampler for the pitch. Not as clean as the
    Rubber Band render, which replaces it as soon as it's ready, but it reacts at once.
    """
    N = 2048        # grain length (46 ms)
    HS = 512        # output hop (75 % overlap)
    TOL = 384       # how far a grain may move to line up
    DEC = 4         # decimation for the alignment search

    def __init__(self, fetch):
        self.fetch = fetch      # fetch(start, n) -> (n, 2) float32 source mix
        self.win = np.hanning(self.N).astype(np.float32)[:, None]
        self.speed, self.ratio = 1.0, 1.0
        self.reset(0.0)

    def set_params(self, speed, semitones):
        self.speed = float(speed)
        self.ratio = float(2 ** (semitones / 12))

    def reset(self, src_pos):
        alpha = self.speed / self.ratio
        warm = (self.N // self.HS) - 1
        self.pa = float(src_pos) - warm * alpha * self.HS
        self.prev = None
        self.acc = np.zeros((self.N, 2), np.float32)
        self.out = np.zeros((0, 2), np.float32)
        self.rpos = 0.0
        for _ in range(warm):  # fill the overlap-add so output starts at full level
            self._hop(keep=False)

    def _hop(self, keep=True):
        N, HS, TOL, DEC = self.N, self.HS, self.TOL, self.DEC
        start = int(round(self.pa))
        delta = 0
        if self.prev is not None:
            region = self.fetch(start - TOL, N + 2 * TOL).mean(axis=1)[::DEC]
            if np.any(region):
                corr = np.correlate(region, self.prev[::DEC], "valid")
                delta = (int(np.argmax(corr)) - TOL // DEC) * DEC
        seg = self.fetch(start + delta, N + HS)
        self.acc += seg[:N] * self.win
        emit = self.acc[:HS] * 0.5   # Hann at 75 % overlap sums to 2
        self.acc = np.concatenate([self.acc[HS:], np.zeros((HS, 2), np.float32)])
        self.prev = seg[HS:HS + N].mean(axis=1)
        self.pa += (self.speed / self.ratio) * HS
        if keep:
            self.out = np.concatenate([self.out, emit])

    def read(self, frames):
        r = self.ratio
        need = int(self.rpos + frames * r) + 2
        while len(self.out) < need:
            self._hop()
        idx = self.rpos + np.arange(frames) * r
        i0 = idx.astype(np.int64)
        fr = (idx - i0).astype(np.float32)[:, None]
        y = self.out[i0] * (1 - fr) + self.out[i0 + 1] * fr
        self.rpos += frames * r
        drop = int(self.rpos)
        if drop > 0:
            self.out = self.out[drop:]
            self.rpos -= drop
        return y.astype(np.float32)


class Player:
    """Mixes all tracks live.

    The clock is the position in the original audio (src_pos). When speed/pitch change,
    playback switches straight away to the real-time stretcher, while the high-quality
    Rubber Band version renders in the background; when that's ready it crossfades over.
    """
    FADE = 512

    def __init__(self):
        self.lock = threading.RLock()
        self.tracks = []
        self.playing = False
        self.loop = False
        self.region = None      # loop area (start, end) in original-audio samples
        self.loop_fade = LOOP_FADE  # seconds
        self.src_pos = 0.0      # position in the original audio, in samples
        self.master = 1.0       # linear master gain
        self.speed = 1.0        # effective rate: original samples per output sample
        self.semitones = 0.0    # total pitch in semitones (coarse + cents/100)
        self.rb = (1.0, 0.0, 0.0)  # render settings: Rubber Band speed, semitones, varispeed cents
        self.clip = False       # latched until cleared
        self._limit_gain = 1.0
        self._meter = np.zeros(2, np.float32)
        self.stream = None
        self.device_error = SD_ERROR
        self.render_busy = 0
        self.render_error = None
        self._gen = 0
        self._pool = ThreadPoolExecutor(max_workers=max(2, min(4, (os.cpu_count() or 2) // 2)))
        self.on_render_done = None   # callback(), called from a worker thread
        self.live = LiveStretcher(self._fetch_mix)
        self.mode = "direct"         # "direct" = buffers at 1:1, "live" = real-time stretcher
        self._live_dirty = True

    # --- audio device ---
    def open_stream(self):
        if sd is None:
            return False
        try:
            self.stream = sd.OutputStream(samplerate=SR, channels=2, dtype="float32",
                                          latency="high", callback=self._callback)
            self.stream.start()
            self.device_error = None
            return True
        except Exception as e:
            self.stream = None
            self.device_error = str(e) or "No audio output device"
            return False

    def close(self):
        try:
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
        self._pool.shutdown(wait=False, cancel_futures=True)

    # --- tracks ---
    def add(self, track):
        with self.lock:
            self.tracks.append(track)
            self._live_dirty = True
        self.request_render()

    def remove(self, track):
        with self.lock:
            if track in self.tracks:
                self.tracks.remove(track)
            if not self.tracks:
                self.playing = False
                self.src_pos = 0.0
            self.src_pos = min(self.src_pos, self.source_length())
            self._live_dirty = True

    def clear(self):
        with self.lock:
            self.tracks = []
            self.playing = False
            self.region = None
            self.src_pos = 0.0

    def source_length(self):
        return max((len(t.orig) for t in self.tracks), default=0)

    def length(self):
        """Length as heard at the current speed, in samples (for the time display)."""
        return int(self.source_length() / self.speed) if self.tracks else 0

    def position(self):
        n = self.source_length()
        return min(1.0, self.src_pos / n) if n else 0.0

    def seek(self, frac):
        with self.lock:
            self.src_pos = max(0.0, min(1.0, frac)) * self.source_length()
            self._live_dirty = True

    def active_region(self):
        """The loop area, if loop is on and an area is marked."""
        r = self.region
        if self.loop and r and r[1] - r[0] >= SR * 0.25:
            return r
        return None

    def set_region(self, a, b):
        with self.lock:
            if a is None:
                self.region = None
            else:
                n = self.source_length()
                a, b = sorted((max(0.0, min(n, a)), max(0.0, min(n, b))))
                self.region = (a, b) if b - a >= SR * 0.1 else None
            self._live_dirty = True

    def toggle(self):
        with self.lock:
            if not self.tracks:
                return False
            if not self.playing and self.src_pos >= self.source_length() - 1:
                self.src_pos = 0.0
            reg = self.active_region()
            if not self.playing and reg and not (reg[0] <= self.src_pos < reg[1]):
                self.src_pos = reg[0]
            self.playing = not self.playing
            self._live_dirty = True
            return self.playing

    # --- speed / pitch ---
    def key(self):
        sp, st, ct = self.rb
        return (round(sp, 6), round(st, 6), round(ct, 6))

    @property
    def varispeed(self):
        return abs(self.rb[2]) > 1e-6

    def set_live(self, speed, semitones, cents=0.0):
        """Change speed/pitch/fine-tuning now (heard at once through the real-time stretcher)."""
        with self.lock:
            self.rb = (float(speed), float(semitones), float(cents))
            self.speed = chain_rate(speed, cents)
            self.semitones = float(semitones) + float(cents) / 100.0
            self.live.set_params(self.speed, self.semitones)

    def set_stretch(self, speed, semitones, cents=0.0):
        """Change speed/pitch/fine-tuning and start the high-quality render."""
        self.set_live(speed, semitones, cents)
        self.request_render()

    def request_render(self):
        key = self.key()
        with self.lock:
            todo = [t for t in self.tracks if t.buf_key != key]
            self._gen += 1
            gen = self._gen
        if not todo:
            return
        self.render_busy += 1

        def job():
            try:
                self.render_error = None
                results = list(self._pool.map(
                    lambda t: (t, render(t.orig, key[0], key[1], t.vocal, key[2])), todo))
                with self.lock:
                    if gen != self._gen:
                        return  # settings changed again; a newer render is coming
                    for t, buf in results:
                        t.buf, t.buf_key = buf, key
            except Exception as e:  # keep playing the real-time version
                self.render_error = str(e)
            finally:
                self.render_busy -= 1
                if self.on_render_done:
                    self.on_render_done()

        threading.Thread(target=job, daemon=True).start()

    def ready(self):
        """True when the high-quality version of the current settings is playing."""
        key = self.key()
        return bool(self.tracks) and all(t.buf_key == key for t in self.tracks)

    # --- mixing ---
    def gains(self):
        soloing = any(t.solo for t in self.tracks)
        return [0.0 if (t.mute or (soloing and not t.solo)) else t.volume for t in self.tracks]

    def _fetch_mix(self, start, n):
        """Original audio, mixed with the current gains (input for the live stretcher)."""
        out = np.zeros((n, 2), np.float32)
        for t, g in zip(self.tracks, self.gains()):
            if g <= 0:
                continue
            a, b = max(start, 0), min(start + n, len(t.orig))
            if b > a:
                env = t.envelope(np.arange(a, b, dtype=np.float64))
                out[a - start:b - start] += t.orig[a:b] * (g if env is None else env[:, None])
        return out

    def mix_block(self, start, frames):
        """Rendered buffers at 1:1 from buffer index `start`."""
        out = np.zeros((frames, 2), np.float32)
        for t, g in zip(self.tracks, self.gains()):
            if g <= 0:
                continue
            seg = t.buf[start:start + frames]
            if len(seg):
                env = None
                if t.automation_active():
                    k = t.buf_key
                    env = t.envelope((start + np.arange(len(seg), dtype=np.float64)) * chain_rate(k[0], k[2]))
                out[:len(seg)] += seg * (g if env is None else env[:, None])
        return out

    def _direct(self, frames):
        k = self.tracks[0].buf_key
        ks = chain_rate(k[0], k[2])
        return self.mix_block(int(self.src_pos / ks), frames)

    def _fade(self, a, b):
        ramp = np.linspace(0.0, 1.0, len(a), dtype=np.float32)[:, None]
        return a * (1 - ramp) + b * ramp

    def render_block(self, frames):
        """Next block of the mix (before master gain). Advances the clock."""
        if self.ready():
            block = self._direct(frames)
            if self.mode == "live" and not self._live_dirty:
                block = self._fade(self.live.read(frames), block)  # hand over smoothly
            self.mode = "direct"
        else:
            if self.mode == "live" and not self._live_dirty:
                block = self.live.read(frames)
            else:
                old = self._direct(frames) if self.mode == "direct" and not self._live_dirty else None
                self.live.reset(self.src_pos)
                block = self.live.read(frames)
                if old is not None:
                    block = self._fade(old, block)
            self.mode = "live"
        self._live_dirty = False
        self.src_pos += frames * self.speed
        return block

    def _callback(self, outdata, frames, time_info, status):
        with self.lock:
            if not self.playing or not self.tracks:
                outdata.fill(0)
                return
            reg = self.active_region()
            if reg and not (reg[0] <= self.src_pos < reg[1]):
                self.src_pos = reg[0]          # loop is on: stay inside the area
                self._live_dirty = True
            start, speed = self.src_pos, self.speed
            block = self.render_block(frames) * self.master
            n = self.source_length()
            if reg:
                block *= region_gain(start + np.arange(frames) * speed, *reg, self.loop_fade)[:, None]
                if self.src_pos >= reg[1]:
                    self.src_pos = reg[0] + (self.src_pos - reg[1])
                    self._live_dirty = True
            elif self.src_pos >= n:
                if self.loop and n:
                    self.src_pos -= n
                else:
                    self.src_pos = float(n)
                    self.playing = False
                self._live_dirty = True
            outdata[:] = self.process_master(block)

    def process_master(self, block):
        """Clip detection (latched), meters and a safety limiter."""
        peak = float(np.abs(block).max()) if block.size else 0.0
        if peak > 1.0:
            self.clip = True
        self._meter = np.maximum(self._meter, np.abs(block).max(axis=0) if block.size else 0)
        target = min(1.0, LIMIT / peak) if peak > 0 else 1.0
        if target < self._limit_gain:
            self._limit_gain = target                       # instant attack
        else:
            self._limit_gain = min(target, self._limit_gain + 0.02)  # slow release
        return block * self._limit_gain

    def take_meter(self):
        """Peak per channel since the last call (for the meters)."""
        m = self._meter.copy()
        self._meter[:] = 0
        return m


# ---------- Auto 440 ----------

def analyse_tuning(tracks):
    """Returns (correction_cents, detected_A_hz or None, confidence)."""
    if not tracks:
        return 0.0, None, 0.0
    n = max(len(t.orig) for t in tracks)
    mono = np.zeros(n, np.float32)
    for t in tracks:
        mono[:len(t.orig)] += t.orig.mean(axis=1)
    offset, conf = tuning.estimate_offset_cents(mono, SR)
    corr = tuning.correction_cents(offset, conf)
    a_hz = 440.0 * 2 ** (offset / 1200) if offset is not None else None
    return corr, a_hz, conf


# ---------- export ----------

def _encode(audio, dst, fmt):
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(SR),
           "-ac", "2", "-i", "-", "-af", EXPORT_LIMITER]
    if fmt == "MP3":
        cmd += ["-c:a", "libmp3lame", "-b:a", "320k", "-compression_level", "0"]
    elif fmt == "OPUS":
        cmd += ["-c:a", "libopus", "-b:a", "256k", "-ar", "48000"]
    elif fmt == "FLAC":
        cmd += ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24",
                "-compression_level", "8"]
    else:
        cmd += ["-c:a", "pcm_s24le"]
    dst = Path(dst)
    tmp = dst.with_name(dst.stem + ".part" + dst.suffix)
    _run(cmd + [str(tmp)], np.ascontiguousarray(audio, dtype=np.float32).tobytes())
    os.replace(tmp, dst)  # never leave half-written files behind


def unique_path(p):
    p = Path(p)
    if not p.exists():
        return p
    i = 2
    while True:
        q = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists():
            return q
        i += 1


def export(tracks, gains, master, speed, semitones, mode, fmt, dest, progress=lambda f: None,
           name_tags=(), region=None, fade=LOOP_FADE, cents=0.0):
    """mode 'mix': dest is the output file. mode 'each': dest is a folder.
    Renders from the original audio at full quality. Returns the written paths."""
    ext = {"WAV": ".wav", "FLAC": ".flac", "MP3": ".mp3", "OPUS": ".opus"}[fmt]
    written = []

    def piece(t, automation=False):
        rate = chain_rate(speed, cents)
        if region is None:
            seg = render(t.orig, speed, semitones, t.vocal, cents)
            p = np.arange(len(seg), dtype=np.float64) * rate
        else:
            a, b = region
            seg = render_part(t.orig, a, b, speed, semitones, t.vocal, cents)
            p = a + np.arange(len(seg), dtype=np.float64) * rate
            seg = seg * region_gain(p, a, b, fade)[:, None]
        env = t.envelope(p) if automation else None
        return seg if env is None else seg * env[:, None]

    total = len(tracks) + 1
    if mode == "mix":
        mix = None
        for i, (t, g) in enumerate(zip(tracks, gains)):
            progress(i / total)
            if g <= 0:
                continue
            auto = t.automation_active()        # the line replaces the volume slider
            buf = piece(t, auto) * ((master if auto else g * master))
            if mix is None:
                mix = buf.copy()
            else:
                if len(buf) > len(mix):
                    mix = np.vstack([mix, np.zeros((len(buf) - len(mix), 2), np.float32)])
                mix[:len(buf)] += buf
        if mix is None:
            raise RuntimeError("Every track is muted, so there is nothing to export.")
        progress((total - 1) / total)
        dst = Path(dest)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.suffix.lower() != ext:
            dst = dst.with_suffix(ext)
        _encode(mix, dst, fmt)
        written.append(dst)
    else:
        folder = Path(dest)
        folder.mkdir(parents=True, exist_ok=True)
        t_tags = list(name_tags)
        for i, t in enumerate(tracks):
            progress(i / total)
            buf = piece(t) * master
            name = safe_filename("_".join([Path(t.path).stem] + t_tags)) + ext
            dst = unique_path(folder / name)
            _encode(buf, dst, fmt)
            written.append(dst)
    progress(1.0)
    return written


def probe_seconds(path):
    """Duration of a written file (used by the self-tests)."""
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True,
                         text=True, creationflags=_NO_WINDOW).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0
