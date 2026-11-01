"""Laptop side: play a transcription back on one Surge patch, nothing else."""
import json, sys
from surgekit import render, mix

job, out = json.load(open(sys.argv[1])), sys.argv[2]
patch = sys.argv[3] if len(sys.argv) > 3 else "Keys/EP 1"
notes = [(n["pitch"] + 12, 95, n["start"], max(.15, n["end"] - n["start"])) for n in job["notes"]]
print(mix([(render(patch, notes, job["notes"][-1]["end"] + 2), 0)], out))
