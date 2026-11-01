"""Devbox side: hum -> notes + chords as JSON for the laptop's Surge renderer."""
import json, os, subprocess, sys, tempfile
import pitch as P
from produce import REC, CHORDS, pick_chords

src_file = sys.argv[1]
with tempfile.TemporaryDirectory() as d:
    wav = os.path.join(d, "in.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(REC, src_file), "-ac", "1", "-ar", "22050", wav], check=True)
    notes, (tonic_name, mode, _) = P.transcribe(wav)
tonic = P.NAMES.index(tonic_name)
chords = [{"start": s, "end": e, "name": n, "root": (tonic + CHORDS[n][0]) % 12,
           "tones": [(tonic + x) % 12 for x in CHORDS[n]]} for s, e, n in pick_chords(notes, tonic)]
print(json.dumps({"notes": [{k: n[k] for k in ("start", "end", "pitch")} for n in notes],
                  "key": f"{tonic_name} {mode}", "chords": chords}))
