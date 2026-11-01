"""Hum motif -> fast electronic track (laptop side, Surge XT).

usage: python edm.py job.json out.mp3 <style>     style: house | trance
The hum is used as a motif (its note shape), not a literal performance: notes are
re-timed onto a 16th-note grid at club tempo and arranged intro / build / drop / break / drop.
"""
import json, sys
import numpy as np
from scipy.signal import butter, sosfilt
from surgekit import SR, render, mix

STYLES = {
    "house": dict(bpm=128, lead="Leads/Saw Octaves", chords="Polysynths/Smooth Stabs",
                  bass="Basses/Wide Bassline", bass_up=2, arp=None),
    "trance": dict(bpm=140, lead="Leads/Sync Lead", chords="Polysynths/Anthemish 1",
                   bass="Basses/Bass 2", arp="Plucks/FM Pluck"),
}
job, out, style = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
S = STYLES[style]
rng = np.random.default_rng(3)
B = 60 / S["bpm"]; STEP = B / 4                      # beat, 16th
INTRO, BUILD, DROP, BREAK, DROP2 = 4, 4, 8, 4, 8
SECTIONS = [("intro", INTRO), ("build", BUILD), ("drop", DROP), ("break", BREAK), ("drop", DROP2)]
BARS = sum(n for _, n in SECTIONS)
LEN = BARS * 4 * B + 3


def bar_section(bar):
    acc = 0
    for name, n in SECTIONS:
        if bar < acc + n:
            return name, bar - acc, n
        acc += n


def t(bar, step):
    return (bar * 16 + step) * STEP


# ---- harmony: vi IV I V in the hum's key -------------------------------------------------
tonic = "C C# D D# E F F# G G# A A# B".split().index(job["key"].split()[0])
PROG = [(9, "m"), (5, ""), (0, ""), (7, "")]           # Am F C G when the hum is in C


def triad(root, q):
    return [root, root + (3 if q == "m" else 4), root + 7]


# ---- motif: first phrase (the run) + last phrase (the turn), outliers dropped ----------------
phr, cur = [], []
for n in job["notes"]:
    if cur and n["start"] - cur[-1]["end"] > 0.5:
        phr.append(cur); cur = []
    cur.append(n)
phr.append(cur)


def clean(ns):
    p = [n["pitch"] for n in ns]
    p = [x for i, x in enumerate(p) if not (0 < i < len(p) - 1 and abs(x - p[i - 1]) > 7 and abs(x - p[i + 1]) > 7)]
    if p and abs(p[0] - p[1 if len(p) > 1 else 0]) > 7:
        p = p[1:]
    return [x for i, x in enumerate(p) if i == 0 or x != p[i - 1]]


motif = (clean(phr[0]) + clean(phr[-1]))[:16]
shift = 12 * round((74 - np.median(motif)) / 12)    # sit the lead around D5
motif = [m + shift for m in motif]
RHYTHM = [0, 2, 3, 5, 6, 8, 10, 11, 16, 18, 19, 21, 22, 24, 26, 27][:len(motif)]   # syncopated 2-bar riff

lead, chords, bass, arp, kick, clap = [], [], [], [], [], []
for bar in range(BARS):
    sec, i, n = bar_section(bar)
    root, q = PROG[bar % 4]
    tri = triad(tonic + root, q)
    chord_notes = sorted(60 + (x % 12) if (x % 12) < 8 else 48 + (x % 12) for x in tri)
    bass_root = 36 + (tonic + root) % 12 + 12 * S.get("bass_up", 1)   # Surge bass patches sit 1–2 octaves low
    full = sec == "drop"
    # lead riff: drops, plus a teaser in the second half of the build and the break
    if full or (sec == "build" and i >= 2) or sec == "break":
        for k, st in enumerate(RHYTHM):
            if (bar % 2) * 16 <= st < (bar % 2 + 1) * 16:
                ln = 3 if k in (len(RHYTHM) - 1, 7) else 1.6
                lead.append((motif[k], 100 if full else 75, t(bar, st % 16), ln * STEP))
    # chords: offbeat stabs in drops and build, long pads in the break
    if sec == "break":
        chords += [(m, 70, t(bar, 0), 4 * B) for m in chord_notes]
    elif full or sec == "build":
        hits = [2, 6, 10, 14] if style == "house" else [0, 3, 6, 10, 12]
        chords += [(m, 95 if full else 70, t(bar, h), 1.5 * STEP) for h in hits for m in chord_notes]
    # bass
    if full:
        if style == "house":
            bass += [(bass_root + (12 if s in (6, 14) else 0), 105, t(bar, s), 1.6 * STEP) for s in range(0, 16, 2)]
        else:
            bass += [(bass_root, 105, t(bar, s), 1.5 * STEP) for s in (2, 6, 10, 14)]
    # trance arp: 16ths up through the chord over two octaves
    if S["arp"] and sec != "break":
        seq = chord_notes + [x + 12 for x in chord_notes]
        arp += [(seq[s % len(seq)], 85 if s % 4 == 0 else 65, t(bar, s), .8 * STEP) for s in range(16)]
    # drums
    if sec in ("intro", "drop") or (sec == "build" and i < n - 1):
        kick += [(36, 120, t(bar, b * 4), .25) for b in range(4)]
    if full:
        clap += [(48, 110, t(bar, 4), .2), (48, 110, t(bar, 12), .2)]
    if sec == "build":   # snare roll: quarters, eighths, sixteenths, then 32nds
        div = [4, 2, 1, .5][i]
        for k in range(int(16 / div)):
            clap.append((48, int(60 + 60 * (i * 16 + k * div) / 64), t(bar, k * div), .12))


def noise_hits(times, decay, hp, gain):
    buf = np.zeros(int(LEN * SR)); sos = butter(4, hp, "highpass", fs=SR, output="sos")
    ln = int(decay * 6 * SR); shape = np.exp(-np.arange(ln) / (decay * SR))
    for tt, v in times:
        s = int(tt * SR); hit = sosfilt(sos, rng.standard_normal(ln)) * shape * v * gain
        buf[s:s + ln] += hit[:max(0, len(buf) - s)]
    return np.stack([buf * .9, buf])


hat_times, open_times = [], []
for bar in range(BARS):
    sec, i, n = bar_section(bar)
    if sec == "break":
        continue
    open_times += [(t(bar, b * 4 + 2), 1) for b in range(4)]
    if sec == "drop":
        hat_times += [(t(bar, s), .5 if s % 2 else .8) for s in range(16)]

# riser: noise swelling over the build, brightening as it goes
start, end = INTRO * 4 * B, (INTRO + BUILD) * 4 * B
r = rng.standard_normal(int((end - start) * SR)); ramp = np.linspace(0, 1, len(r)) ** 2
r = sosfilt(butter(2, 2000, "highpass", fs=SR, output="sos"), r) * ramp
riser = np.zeros(int(LEN * SR)); riser[int(start * SR):int(start * SR) + len(r)] = r
riser = np.stack([riser, riser])

# sidechain: duck everything melodic on each kick
duck = np.ones(int(LEN * SR))
dk = 1 - 0.75 * np.exp(-np.arange(int(B * SR)) / (0.09 * SR))
for _, _, tt, _ in kick:
    s = int(tt * SR); duck[s:s + len(dk)] = np.minimum(duck[s:s + len(dk)], dk[:len(duck) - s])


def sc(a):
    return a * duck[:a.shape[1]]


stems = [
    (sc(render(S["lead"], lead, LEN)), -1, "lead"),
    (sc(render(S["chords"], chords, LEN)), -4, "chords"),
    (sc(render(S["bass"], bass, LEN)), -2, "bass"),
    (render("Percussion/Kick Tech 1", kick, LEN), 1, "kick"),
    (render("Percussion/Snare Tight", clap, LEN), -5, "clap"),
    (noise_hits(hat_times, .012, 8000, 1) + noise_hits(open_times, .06, 7000, 1.3), -9, "hats"),
    (riser, -12, "riser"),
]
if S["arp"]:
    stems.append((sc(render(S["arp"], arp, LEN)), -7, "arp"))
for a, _, nm in stems:
    m = a.mean(0); s = np.abs(np.fft.rfft(m)); f = np.fft.rfftfreq(len(m), 1 / SR); k = (f > 25) & (f < 3000)
    print(f"{nm:7} rms {np.sqrt((a ** 2).mean()):.4f}  peak {f[k][np.argmax(s[k])]:7.1f} Hz")
print(f"motif {motif}  bpm {S['bpm']}  bars {BARS}  {LEN:.1f}s")
print(mix([(a, db) for a, db, _ in stems], out))
