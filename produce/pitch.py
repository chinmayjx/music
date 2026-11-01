"""Hum -> pitch contour -> notes, in plain numpy (YIN pitch tracking)."""
import wave
import numpy as np

HOP = 256


def read_wav(path):
    with wave.open(path) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return x, sr


def yin(x, sr, fmin=70, fmax=900, frame=2048, hop=HOP, thresh=0.15):
    """Returns (times, midi or nan, rms) per frame."""
    tmin, tmax = int(sr / fmax), int(sr / fmin)
    n = 1 + max(0, (len(x) - frame) // hop)
    times, midi, rms = np.zeros(n), np.full(n, np.nan), np.zeros(n)
    for i in range(n):
        f = x[i * hop: i * hop + frame]
        times[i] = (i * hop + frame / 2) / sr
        rms[i] = np.sqrt((f ** 2).mean())
        w = frame // 2
        # difference function via autocorrelation
        fx = np.fft.rfft(f, 2 * frame)
        acf = np.fft.irfft(fx * np.conj(fx))[:w]
        cs = np.concatenate([[0], np.cumsum(f ** 2)])
        e0 = cs[w] - cs[0]
        etau = cs[np.arange(w) + w] - cs[np.arange(w)]
        d = e0 + etau - 2 * acf
        d[0] = 0
        cmnd = d * np.arange(w) / np.maximum(np.cumsum(d), 1e-12)
        cmnd[0] = 1
        seg = cmnd[tmin:tmax]
        below = np.where(seg < thresh)[0]
        if not len(below):
            continue
        t = below[0]
        while t + 1 < len(seg) and seg[t + 1] < seg[t]:
            t += 1
        tau = t + tmin
        if 0 < tau < w - 1:  # parabolic interpolation
            a, b, c = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
            tau = tau + 0.5 * (a - c) / (a - 2 * b + c + 1e-12)
        midi[i] = 69 + 12 * np.log2(sr / tau / 440)
    gate = rms > max(0.01, 0.12 * np.percentile(rms, 95))
    midi[~gate] = np.nan
    return times, midi, rms


def median(a, k=5):
    out = a.copy()
    for i in range(len(a)):
        w = a[max(0, i - k // 2): i + k // 2 + 1]
        w = w[~np.isnan(w)]
        out[i] = np.median(w) if len(w) > k // 2 and not np.isnan(a[i]) else np.nan
    return out


def tuning_offset(midi):
    """Hummers are rarely at A440: find the cents offset that best fits a 12-note grid."""
    v = midi[~np.isnan(midi)]
    cands = np.linspace(-0.5, 0.5, 101)
    return cands[np.argmin([np.mean(np.abs(((v - c) + 0.5) % 1 - 0.5)) for c in cands])]


def segment(times, midi, min_len=0.09, hop_s=None):
    """Split the smoothed contour into notes: a new note when the rounded pitch changes and holds."""
    hop_s = hop_s or (times[1] - times[0])
    notes, cur = [], None
    r = np.round(midi)
    for i, (t, m) in enumerate(zip(times, r)):
        if np.isnan(m):
            if cur: notes.append(cur); cur = None
            continue
        if cur and m == cur["pitch"]:
            cur["end"] = t + hop_s; cur["raw"].append(midi[i]); continue
        # pitch changed: only switch if the new pitch holds for ~3 frames (ignores scoops)
        ahead = r[i:i + 3]
        if cur and not np.all(ahead == m):
            cur["end"] = t + hop_s; cur["raw"].append(midi[i]); continue
        if cur: notes.append(cur)
        cur = {"pitch": m, "start": t, "end": t + hop_s, "raw": [midi[i]]}
    if cur: notes.append(cur)
    notes = [n for n in notes if n["end"] - n["start"] >= min_len]
    # merge repeated same-pitch notes split by tiny gaps
    merged = []
    for n in notes:
        if merged and n["pitch"] == merged[-1]["pitch"] and n["start"] - merged[-1]["end"] < 0.06:
            merged[-1]["end"] = n["end"]; merged[-1]["raw"] += n["raw"]
        else:
            merged.append(n)
    for n in merged:
        n["hz_midi"] = float(np.median(n["raw"])); n["pitch"] = int(round(n["hz_midi"])); del n["raw"]
    return merged


NAMES = "C C# D D# E F F# G G# A A# B".split()


def name(m):
    return f"{NAMES[int(m) % 12]}{int(m) // 12 - 1}"


def key_of(notes):
    """Krumhansl key profiles, weighted by duration."""
    maj = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    mnr = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    h = np.zeros(12)
    for n in notes:
        h[n["pitch"] % 12] += n["end"] - n["start"]
    best = max(((np.corrcoef(h, np.roll(p, k))[0, 1], k, q) for k in range(12) for p, q in ((maj, "major"), (mnr, "minor"))))
    return best[1], best[2], best[0]


def plateaus(times, midi, jump=0.6, hold=3, gap=3, min_len=0.08):
    """Notes as held pitch regions: a new note starts when pitch moves > `jump` semitones
    from the current note's median and stays there for `hold` frames."""
    hop_s = times[1] - times[0]
    notes, cur, pend, miss = [], [], [], 0
    def close():
        if cur and (times[cur[-1]] - times[cur[0]] + hop_s) >= min_len:
            notes.append({"start": times[cur[0]], "end": times[cur[-1]] + hop_s,
                          "hz_midi": float(np.median(midi[cur]))})
    for i, m in enumerate(midi):
        if np.isnan(m):
            miss += 1
            if miss >= gap:
                close(); cur, pend = [], []
            continue
        miss = 0
        if not cur:
            cur = [i]; continue
        if abs(m - np.median(midi[cur])) <= jump:
            cur += pend + [i]; pend = []
        else:
            pend.append(i)
            if len(pend) >= hold and np.ptp(midi[pend]) <= jump:
                close(); cur, pend = pend, []
    close()
    return notes


MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]


def snap_to_scale(notes):
    """Pick tonic, mode and tuning offset that put the held notes closest to a scale; snap them."""
    v = np.array([n["hz_midi"] for n in notes]); w = np.array([n["end"] - n["start"] for n in notes])
    best = None
    for off in np.linspace(-0.5, 0.5, 21):
        for tonic in range(12):
            for mode, sc in (("major", MAJOR), ("minor", MINOR)):
                grid = np.array([tonic + s + 12 * o for o in range(-1, 11) for s in sc])
                d = np.abs((v - off)[:, None] - grid[None]).min(1)
                cost = (d * w).sum()
                if best is None or cost < best[0]:
                    best = (cost, off, tonic, mode, grid)
    _, off, tonic, mode, grid = best
    for n in notes:
        n["pitch"] = int(grid[np.argmin(np.abs(grid - (n["hz_midi"] - off)))])
    return NAMES[tonic], mode, off


def transcribe(path):
    """WAV -> (notes, (tonic, mode, offset)). Fine segmentation, then snap to the best-fitting scale."""
    x, sr = read_wav(path)
    t, m, _ = yin(x, sr)
    ms = median(m)
    notes = segment(t, ms)
    key = snap_to_scale(notes)
    out = []
    for n in notes:  # snapping can make neighbours equal: merge them
        if out and n["pitch"] == out[-1]["pitch"] and n["start"] - out[-1]["end"] < 0.12:
            out[-1]["end"] = n["end"]
        else:
            out.append(n)
    return out, key
