"""Laptop side: render a hum job (notes + chords JSON) with Surge XT patches."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "studio"))
import json, sys
from surgekit import render, mix

job = json.load(open(sys.argv[1])); out = sys.argv[2]
end = job["notes"][-1]["end"] + 3
lead = [(n["pitch"] + 12, 90, n["start"], max(.12, n["end"] - n["start"])) for n in job["notes"]]
keys, bass = [], []
for c in job["chords"]:
    voicing = sorted(60 + t if t < 7 else 48 + t for t in c["tones"])   # keep chords around middle C
    keys += [(m, 62, c["start"] + i * .015, c["end"] - c["start"]) for i, m in enumerate(voicing)]
    bass.append((48 + c["root"] - (12 if c["root"] > 4 else 0) + 12, 90, c["start"], c["end"] - c["start"]))  # +12: Mellow plays an octave down
print(mix([(render("Plucks/Nice Pluck 2", lead, end), 0),
           (render("Keys/EP 1", keys, end), -5),
           (render("Basses/Mellow", bass, end), -6)], out))
