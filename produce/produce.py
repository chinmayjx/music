"""Hum recording -> notes -> two renders (melody only, arranged), saved next to the recordings.

usage: python3 produce.py <recording file in the recordings dir>
"""
import json, os, subprocess, sys, tempfile, wave
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pitch as P

SR = 44100
REC = os.path.expanduser("~/data/music/recordings")
HERE = os.path.dirname(os.path.abspath(__file__))


def hz(m):
    return 440 * 2 ** ((m - 69) / 12)


def env(n, a=0.01, d=0.15, s=0.6, r=0.25):
    """ADSR over n samples of note-on, plus release tail."""
    A, D, R = int(a * SR), int(d * SR), int(r * SR)
    on = np.concatenate([np.linspace(0, 1, A), np.linspace(1, s, D), np.full(max(0, n - A - D), s)])[:n]
    return np.concatenate([on, np.linspace(on[-1] if len(on) else 0, 0, R)])


def voice(freq, dur, harmonics, vib=0.0, **adsr):
    e = env(int(dur * SR), **adsr)
    t = np.arange(len(e)) / SR
    ph = 2 * np.pi * freq * t + (vib * np.sin(2 * np.pi * 5.2 * t) * np.minimum(t / 0.4, 1) if vib else 0)
    return sum(a * np.sin(k * ph) for k, a in harmonics) * e


LEAD = [(1, 1), (2, .35), (3, .18), (4, .06), (5, .04)]           # soft flute / EP-ish
PAD = [(1, 1), (2, .5), (3, .33), (4, .25), (5, .2), (6, .16)]     # mellow saw, few partials
BASS = [(1, 1), (2, .3), (3, .08)]


def place(buf, sig, start):
    s = int(start * SR); buf[s:s + len(sig)] += sig[:max(0, len(buf) - s)]


def reverb(x, secs=2.2, mix=.22):
    n = int(secs * SR)
    ir = np.random.default_rng(1).standard_normal(n) * np.exp(-np.arange(n) / (secs / 6.9 * SR))
    ir[:int(.012 * SR)] = 0
    m = len(x) + n
    wet = np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)[:len(x)]
    wet *= np.sqrt((x ** 2).mean()) / (np.sqrt((wet ** 2).mean()) + 1e-9)
    return (1 - mix) * x + mix * wet


CHORDS = {"I": [0, 4, 7], "ii": [2, 5, 9], "iii": [4, 7, 11], "IV": [5, 9, 0], "V": [7, 11, 2], "vi": [9, 0, 4]}


def pick_chords(notes, tonic, window=1.2):
    """Per phrase, cut into ~window-second slots and pick the chord whose tones cover the most sung time."""
    phrases, cur = [], []
    for n in notes:
        if cur and n["start"] - cur[-1]["end"] > 0.5:
            phrases.append(cur); cur = []
        cur.append(n)
    phrases.append(cur)
    out = []
    for ph in phrases:
        a, b = ph[0]["start"], ph[-1]["end"]
        k = max(1, round((b - a) / window)); edges = np.linspace(a, b, k + 1)
        prev = None
        for i in range(k):
            s, e = edges[i], edges[i + 1]
            def score(name):
                tones = {(tonic + x) % 12 for x in CHORDS[name]}
                sc = sum(min(e, n["end"]) - max(s, n["start"]) for n in ph
                         if n["pitch"] % 12 in tones and min(e, n["end"]) > max(s, n["start"]))
                return (sc + (0.15 if name == "I" and i in (0, k - 1) else 0) + (0.12 if name in ("I", "IV", "V") else 0)
                        - (0.1 if name == prev else 0))
            prev = max(CHORDS, key=score)
            out.append((s, e + (0.6 if i == k - 1 else 0), prev))
    return out


def write_mp3(x, path):
    x = np.tanh(x * 1.2); x *= 0.89 / (np.abs(x).max() + 1e-9)
    st = np.stack([x, x], 1) if x.ndim == 1 else x.T
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((st * 32767).astype(np.int16).tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name, "-b:a", "192k", path], check=True)


def save(x, src_file, label, src_meta, extra):
    tz = ZoneInfo("Asia/Kolkata"); now = datetime.now(tz)
    base = os.path.splitext(src_file)[0]
    f = f"{base}__{label.lower().replace(' ', '-')}.mp3"
    write_mp3(x, os.path.join(REC, f))
    meta = {"name": f"{src_meta.get('name', 'hum')} → {label}", "created": now.isoformat(timespec="seconds"),
            "mime": "audio/mpeg", "duration": round(x.shape[-1] / SR, 1), "source": "claude", "from": src_file}
    meta.update(extra)
    json.dump(meta, open(os.path.join(REC, f + ".json"), "w"))
    return f


def main(src_file):
    src = os.path.join(REC, src_file)
    src_meta = json.load(open(src + ".json")) if os.path.exists(src + ".json") else {}
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "in.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "22050", wav], check=True)
        notes, (tonic_name, mode, _) = P.transcribe(wav)
    tonic = P.NAMES.index(tonic_name)
    end = notes[-1]["end"] + 2.5
    melody = np.zeros(int(end * SR))
    for n in notes:  # an octave above the hum: hums sit low, instruments sound better higher
        dur = max(.12, n["end"] - n["start"])
        place(melody, voice(hz(n["pitch"] + 12), dur, LEAD, vib=.004, a=.015, d=.2, s=.7, r=.3) * .5, n["start"])
    chords = pick_chords(notes, tonic)
    pad, bass = np.zeros_like(melody), np.zeros_like(melody)
    for s, e, name in chords:
        root = 48 + (tonic + CHORDS[name][0]) % 12
        for iv in CHORDS[name]:
            m = 48 + (tonic + iv) % 12
            for det in (-.08, .08):
                place(pad, voice(hz(m) * 2 ** (det / 12), e - s, PAD, a=.25, d=.3, s=.8, r=.6) * .07, s)
        place(bass, voice(hz(root - 12), e - s, BASS, a=.01, d=.25, s=.6, r=.2) * .35, s)
    lab = " ".join(P.name(n["pitch"]) for n in notes)
    info = {"notes": lab, "key": f"{tonic_name} {mode}", "chords": " ".join(c for _, _, c in chords)}
    a = save(reverb(melody, mix=.15), src_file, "melody", src_meta, info)
    b = save(reverb(melody + pad + bass), src_file, "arranged", src_meta, info)
    print(json.dumps({"files": [a, b], **info}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
