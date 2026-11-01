"""studio: music rendering and transcription over HTTP, for artifacts and agents on the tailnet.

GET  /health
GET  /instruments                 Surge XT factory patches by category, plus builtins
POST /render?format=mp3|wav       body: a song spec (see engine.py) -> audio; cached by spec
GET  /renders/<id>.<fmt>          a cached render
POST /transcribe                  multipart: file (any audio), scale=true|false, bpm=<optional> -> notes
"""
import hashlib, json, os, socket, subprocess, tempfile
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
import engine, pitch, surgekit

CACHE = os.path.expanduser(os.environ.get("STUDIO_CACHE", "~/.cache/studio/renders"))
MIME = {"mp3": "audio/mpeg", "wav": "audio/wav"}
os.makedirs(CACHE, exist_ok=True)

app = FastAPI(title="studio")
# Tailnet-only service: being on the tailnet is the auth. Sandboxed artifacts send Origin: null.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Render-Id", "X-Duration"])


@app.get("/health")
def health():
    return {"ok": True, "host": socket.gethostname(), "surge": os.path.exists(surgekit.SURGE)}


@app.get("/instruments")
def instruments():
    return engine.instruments()


@app.post("/render")
async def render(request: Request, format: str = "mp3"):
    if format not in MIME:
        raise HTTPException(400, "format must be mp3 or wav")
    try:
        spec = await request.json()
    except ValueError:
        raise HTTPException(400, "body must be a JSON song spec")
    rid = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
    path = os.path.join(CACHE, f"{rid}.{format}")
    meta = path + ".json"
    if not os.path.exists(path):
        try:
            stems, seconds = await run(engine.render, spec)
        except engine.SpecError as e:
            raise HTTPException(400, str(e))
        data = surgekit.encode(surgekit.master(stems), format)
        with open(path, "wb") as f:
            f.write(data)
        with open(meta, "w") as f:
            json.dump({"seconds": round(seconds, 2)}, f)
    seconds = json.load(open(meta))["seconds"] if os.path.exists(meta) else None
    return FileResponse(path, media_type=MIME[format],
                        headers={"X-Render-Id": rid, "X-Duration": str(seconds or "")})


@app.get("/renders/{name}")
def cached(name: str):
    rid, _, fmt = name.partition(".")
    path = os.path.join(CACHE, f"{rid}.{fmt}")
    if fmt not in MIME or not rid.isalnum() or not os.path.exists(path):
        raise HTTPException(404, "no such render")
    return FileResponse(path, media_type=MIME[fmt])


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...), scale: bool = Form(True), bpm: float | None = Form(None)):
    with tempfile.TemporaryDirectory() as d:
        src, wav = os.path.join(d, "in"), os.path.join(d, "in.wav")
        with open(src, "wb") as f:
            f.write(await file.read())
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "22050", wav],
                           capture_output=True, text=True)
        if r.returncode:
            raise HTTPException(400, "could not decode audio: " + r.stderr.strip()[:200])
        notes, key = await run(pitch.transcribe, wav, scale)
    out = [{"pitch": n["pitch"], "name": pitch.name(n["pitch"]), "start": round(n["start"], 3),
            "end": round(n["end"], 3), **({"start_beat": round(n["start"] * bpm / 60, 3),
                                           "dur_beats": round((n["end"] - n["start"]) * bpm / 60, 3)} if bpm else {})}
           for n in notes]
    return {"notes": out, "key": f"{key[0]} {key[1]}", "snapped_to_scale": scale}


async def run(fn, *a):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(fn, *a)
