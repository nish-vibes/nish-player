"""Auto 440 (beta): estimate how far a recording sits from A = 440 Hz equal temperament.

Finds spectral peaks, measures how far each one is from the nearest equal-tempered
semitone, and takes a magnitude-weighted circular average of those deviations.
Returns cents: +18 means the recording is 18 cents sharp (so correct by -18).
"""
import numpy as np


def estimate_offset_cents(x, sr, fmin=100.0, fmax=1500.0, max_seconds=120):
    """x: mono float array. Returns (offset_cents, confidence 0..1) or (None, 0)."""
    x = np.asarray(x, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    n_max = int(max_seconds * sr)
    if len(x) > n_max:  # analyse the middle of the song
        start = (len(x) - n_max) // 2
        x = x[start:start + n_max]
    N, hop = 8192, 4096
    if len(x) < N:
        return None, 0.0
    frames = 1 + (len(x) - N) // hop
    win = np.hanning(N).astype(np.float32)
    lo = max(2, int(fmin * N / sr))
    hi = min(N // 2 - 2, int(fmax * N / sr))

    num = 0j
    den = 0.0
    for f0 in range(0, frames, 64):  # in blocks to keep memory small
        idx = np.arange(N)[None, :] + hop * np.arange(f0, min(frames, f0 + 64))[:, None]
        S = np.abs(np.fft.rfft(x[idx] * win, axis=1))
        frame_peak = S.max(axis=1, keepdims=True) + 1e-12
        c = S[:, lo:hi]
        l = S[:, lo - 1:hi - 1]
        r = S[:, lo + 1:hi + 1]
        peak = (c > l) & (c >= r) & (c > 0.05 * frame_peak)
        if not peak.any():
            continue
        a, b, g = np.log(l + 1e-12), np.log(c + 1e-12), np.log(r + 1e-12)
        denom = a - 2 * b + g
        denom = np.where(np.abs(denom) < 1e-9, -1e-9, denom)
        p = np.clip(0.5 * (a - g) / denom, -0.5, 0.5)
        bins = np.arange(lo, hi)[None, :] + p
        freq = bins * sr / N
        cents = 1200.0 * np.log2(np.maximum(freq, 1e-6) / 440.0)
        dev = cents - 100.0 * np.round(cents / 100.0)
        w = c[peak]
        ang = 2 * np.pi * dev[peak] / 100.0
        num += np.sum(w * np.exp(1j * ang))
        den += float(np.sum(w))
    if den <= 0:
        return None, 0.0
    offset = float(np.angle(num) * 100.0 / (2 * np.pi))
    confidence = float(abs(num) / den)
    return round(offset, 1), round(confidence, 3)


def correction_cents(offset, confidence, min_confidence=0.12, max_abs=50):
    """How many cents to shift so the song lands on A440, or 0 if unsure."""
    if offset is None or confidence < min_confidence:
        return 0.0
    return float(max(-max_abs, min(max_abs, -offset)))
