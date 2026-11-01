"""Track 01 — lo-fi loop, 85 BPM, ii–V–I–VI in C (Dm9 · G13 · Cmaj9 · A7b13)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "studio"))
import random
import numpy as np
from scipy.signal import butter, sosfilt
from surgekit import SR, render, mix

random.seed(7)
BPM = 85
B = 60 / BPM                       # one beat in seconds
BARS = 16
LEN = BARS * 4 * B + 3             # tail for reverb


def t(bar, beat):
    return (bar * 4 + beat) * B


def swing(beat):
    """Push off-beat eighths late, for a laid-back feel."""
    return beat + (1 / 6 if abs(beat % 1 - 0.5) < 1e-6 else 0)


def hum(v, spread=8):
    return v + random.randint(-spread, spread)


CHORDS = [  # rootless voicings, bass root (+12: the Mellow patch plays an octave down)
    ([53, 57, 60, 64], 38 + 12),   # Dm9
    ([53, 57, 59, 64], 43 + 12),   # G13
    ([52, 55, 59, 62], 36 + 12),   # Cmaj9
    ([55, 61, 65, 70], 45 + 12),   # A7b13
]
MELODY = [  # (bar in phrase, beat, midi, length in beats)
    (0, 0, 76, 1), (0, 1.5, 74, .5), (0, 2, 72, 1), (0, 3, 69, 1),
    (1, .5, 71, .5), (1, 1, 74, 1), (1, 2.5, 76, 1.5),
    (2, 0, 79, 1.5), (2, 1.5, 76, .5), (2, 2, 74, .5), (2, 2.5, 76, 1.5),
    (3, 0, 73, 1), (3, 1, 76, .5), (3, 2, 77, 1), (3, 3, 76, 1),
]

keys, pad, bass, lead, kick, snare = [], [], [], [], [], []
for bar in range(BARS):
    voicing, root = CHORDS[bar % 4]
    intro, outro = bar < 4, bar >= 12
    # keys: lazy strum on beat 1, soft re-hit on the "and" of 3
    for i, n in enumerate(voicing):
        keys.append((n, hum(70), t(bar, 0) + i * 0.018, 3.4 * B))
        if bar % 2:
            keys.append((n, hum(52), t(bar, swing(3.5)) + i * 0.012, 0.45 * B))
    pad.append((voicing[0] - 12, 60, t(bar, 0), 4 * B))
    pad.append((voicing[2], 50, t(bar, 0), 4 * B))
    if intro:
        continue
    # bass
    bass += [(root, hum(95), t(bar, 0), 1.4 * B),
             (root + 7, hum(80), t(bar, swing(2.5)), 0.4 * B),
             (root, hum(85), t(bar, 3), 0.8 * B)]
    # melody: phrase played twice in the middle, sparse in the outro
    if not outro or bar % 4 < 2:
        for pb, beat, n, ln in MELODY:
            if pb == bar % 4:
                lead.append((n, hum(80, 10), t(bar, swing(beat)) + random.uniform(0, .015), ln * B * .9))
    if outro:
        continue
    kick += [(36, 110, t(bar, 0), .3), (36, 95, t(bar, swing(2.5)), .3)]
    if bar % 4 == 3:
        kick.append((36, 80, t(bar, 3.75), .2))
    snare += [(48, hum(100), t(bar, 1) + .02, .3), (48, hum(100), t(bar, 3) + .02, .3)]


def hats():
    n = int(LEN * SR); out = np.zeros((2, n))
    hp = butter(4, 7000, "highpass", fs=SR, output="sos")
    for bar in range(4, BARS):
        for e in range(8):
            beat = swing(e / 2)
            vel = (0.9 if e % 2 == 0 else 0.55) * random.uniform(.8, 1)
            ln = int(.045 * SR)
            hit = sosfilt(hp, np.random.randn(ln)) * np.exp(-np.arange(ln) / (.012 * SR)) * vel
            s = int(t(bar, beat) * SR)
            out[0, s:s + ln] += hit * .8; out[1, s:s + ln] += hit
    return out


stems = [
    (render("Keys/EP 1", keys, LEN), 0),
    (render("Pads/MKS-70 Warm Pad", pad, LEN), -9),
    (render("Basses/Mellow", bass, LEN), -1),
    (render("Plucks/Lo-Fi Pluck", lead, LEN), -2),
    (render("Percussion/Kick 909ish", kick, LEN), -1),
    (render("Percussion/Snare Tight", snare, LEN), -6),
    (hats(), -10),
]
for (a, _), name in zip(stems, "keys pad bass lead kick snare hats".split()):
    print(f"{name:6} rms {np.sqrt((a**2).mean()):.4f}")
print(mix(stems, "out/track01.mp3", lowpass_hz=11000))
