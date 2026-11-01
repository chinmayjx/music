"""Song spec -> audio. A spec is tempo + tracks of notes, each track on one instrument.

{
  "bpm": 120,                    # used when unit is "beats"
  "unit": "beats",               # or "seconds"
  "tail": 2,                     # seconds of release/reverb after the last note
  "tracks": [
    {"instrument": "Keys/EP 1",  # a Surge XT factory patch (see instruments()), or a builtin: hat, open-hat
     "gain_db": 0,               # tracks are loudness-matched first, then set to this level
     "notes": [{"pitch": 60, "start": 0, "dur": 1, "vel": 100}]}   # pitch: MIDI number or name like "C4", "F#3"
  ]
}
"""
import os, re, threading
import numpy as np
from scipy.signal import butter, sosfilt
import surgekit

SR = surgekit.SR
SKIP = {"MPE", "Templates", "Tutorials", "Vocoder"}
BUILTINS = {"hat": (0.012, 8000), "open-hat": (0.06, 7000)}
_lock = threading.Lock()   # one DawDreamer render at a time
NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


class SpecError(ValueError):
    pass


def instruments():
    out = {}
    for cat in sorted(os.listdir(surgekit.PATCHES)):
        d = os.path.join(surgekit.PATCHES, cat)
        if cat in SKIP or not os.path.isdir(d):
            continue
        out[cat] = sorted(f[:-4] for f in os.listdir(d) if f.endswith(".fxp"))
    out["Builtin"] = sorted(BUILTINS)
    return out


def midi(p):
    if isinstance(p, (int, float)):
        return int(p)
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", str(p).strip())
    if not m:
        raise SpecError(f"bad pitch {p!r}: use a MIDI number or a name like C4, F#3, Bb2")
    n = NAMES[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return n + 12 * (int(m.group(3)) + 1)


def _builtin(name, notes, seconds, rng):
    decay, hp = BUILTINS[name]
    buf = np.zeros(int(seconds * SR)); sos = butter(4, hp, "highpass", fs=SR, output="sos")
    ln = int(decay * 6 * SR); shape = np.exp(-np.arange(ln) / (decay * SR))
    for _, vel, start, _ in notes:
        s = int(start * SR); hit = sosfilt(sos, rng.standard_normal(ln)) * shape * vel / 127
        buf[s:s + ln] += hit[:max(0, len(buf) - s)]
    return np.stack([buf * .9, buf])


def render(spec):
    """Returns (stereo float array (2, n), seconds)."""
    tracks = spec.get("tracks") or []
    if not tracks:
        raise SpecError("spec needs at least one track")
    unit = spec.get("unit", "beats")
    if unit not in ("beats", "seconds"):
        raise SpecError("unit must be beats or seconds")
    scale = 60 / float(spec.get("bpm", 120)) if unit == "beats" else 1.0
    known = {f"{c}/{p}" for c, ps in instruments().items() if c != "Builtin" for p in ps}
    parsed = []
    for i, t in enumerate(tracks):
        inst = t.get("instrument", "")
        if inst not in known and inst not in BUILTINS:
            raise SpecError(f"track {i}: unknown instrument {inst!r} (see GET /instruments)")
        notes = [(midi(n["pitch"]), int(n.get("vel", 100)), float(n["start"]) * scale,
                  max(0.02, float(n.get("dur", 1)) * scale)) for n in t.get("notes", [])]
        if notes:
            parsed.append((inst, notes, float(t.get("gain_db", 0))))
    if not parsed:
        raise SpecError("no notes in any track")
    end = max(s + d for _, notes, _ in parsed for _, _, s, d in notes)
    seconds = min(end + float(spec.get("tail", 2)), 600)
    rng = np.random.default_rng(0)
    stems = []
    with _lock:
        for inst, notes, db in parsed:
            a = _builtin(inst, notes, seconds, rng) if inst in BUILTINS else surgekit.render(inst, notes, seconds)
            stems.append((a, db))
    return stems, seconds
