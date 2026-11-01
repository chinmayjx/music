"""The whole-tone run: keyboard take (A# C D E F# G#) + the voice recording's tempo and phrasing.

Voice (2026-11-01, Voice input artifact): 8 phrases, one every 1.28 s -> one 4/4 bar each = ~187 BPM.
Each phrase: a quick rise, top note held ~a beat. Bars 1-4: A# C D E F# G#. Bars 5-8: the same run a whole
step lower, G# A# C D E F# (the voice starts lower there too; v1 wrongly kept A# and just stopped at F#).
Notes from the keyboard take (whole-tone scale from A#), placed in the voice's register two octaves up.
"""
import json, sys

LEAD = sys.argv[1] if len(sys.argv) > 1 else "Leads/Classic Lead 1"

BPM = 187
RUN = [70, 72, 74, 76, 78, 80]          # A#4 C5 D5 E5 F#5 G#5


def bar_notes(bar, shift=0):
    run = [p + shift for p in RUN]
    out = [{"pitch": p, "start": bar * 4 + i * 0.5, "dur": 0.45, "vel": 100} for i, p in enumerate(run[:-1])]
    out.append({"pitch": run[-1], "start": bar * 4 + (len(run) - 1) * 0.5, "dur": 1.1, "vel": 110})
    return out


INTRO = 1
lead, hats, kick, snare, bass = [], [], [], [], []
for rep in range(2):                      # the 8 bars as hummed, then again with drums and bass
    for b in range(8):
        bar = INTRO + rep * 8 + b
        lead += bar_notes(bar, 0 if b < 4 else -2)
        hats += [{"pitch": 0, "start": bar * 4 + s / 2, "vel": 70 if s % 2 else 100} for s in range(8)]
        if rep == 1:   # drum & bass: kick on 1 and the "and" of 3, snare on 2 and 4
            kick += [{"pitch": 36, "start": bar * 4 + x, "dur": 0.25, "vel": 120} for x in (0, 2.5)]
            snare += [{"pitch": 48, "start": bar * 4 + x, "dur": 0.2, "vel": 110} for x in (1, 3)]
            bass.append({"pitch": 58 if b < 4 else 56, "start": bar * 4, "dur": 3.8, "vel": 100})   # A#1 / G#1 (patch plays 2 octaves down)
hats = [{"pitch": 0, "start": s / 2, "vel": 70 if s % 2 else 100} for s in range(8)] + hats   # count-in bar

spec = {"bpm": BPM, "unit": "beats", "tail": 2, "tracks": [
    {"instrument": LEAD, "gain_db": 0, "notes": lead},
    {"instrument": "hat", "gain_db": -9, "notes": hats},
    {"instrument": "Percussion/Kick Tech 1", "gain_db": 0, "notes": kick},
    {"instrument": "Percussion/Snare Tight", "gain_db": -4, "notes": snare},
    {"instrument": "Basses/Wide Bassline", "gain_db": -3, "notes": bass},
]}
json.dump(spec, sys.stdout)
