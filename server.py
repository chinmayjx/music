#!/usr/bin/env python3
"""Music recorder: a phone page to record or upload audio into the devbox.

GET  /                      the page
GET  /api/files             recordings, newest first
POST /api/upload?name=&duration=   raw audio body (Content-Type = its mime type)
DELETE /api/files/<file>    delete a recording
GET  /files/<file>          the audio (supports Range, so seeking works)
"""
import json, mimetypes, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.expanduser(os.environ.get("MUSIC_DIR", "~/data/music/recordings"))
PORT = int(os.environ.get("PORT", "8792"))
MAX_BYTES = 200 * 1024 * 1024
TZ = ZoneInfo("Asia/Kolkata")
EXT = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/aac": ".aac",
       "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/flac": ".flac",
       "audio/x-m4a": ".m4a", "audio/3gpp": ".3gp", "audio/amr": ".amr", "video/webm": ".webm",
       "video/mp4": ".m4a"}
SAFE = re.compile(r"^[\w.\-]+$")


def slug(s):
    return re.sub(r"[^\w\-]+", "-", s.strip().lower()).strip("-")[:60]


def meta_path(f):
    return os.path.join(DIR, f + ".json")


def listing():
    out = []
    for f in os.listdir(DIR):
        if f.endswith(".json") or f.startswith("."):
            continue
        p = os.path.join(DIR, f)
        m = {}
        if os.path.exists(meta_path(f)):
            with open(meta_path(f)) as fh:
                m = json.load(fh)
        st = os.stat(p)
        out.append({"file": f, "name": m.get("name") or f, "size": st.st_size,
                    "created": m.get("created") or datetime.fromtimestamp(st.st_mtime, TZ).isoformat(timespec="seconds"),
                    "duration": m.get("duration"), "source": m.get("source", "file")})
    return sorted(out, key=lambda x: x["created"], reverse=True)


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def send(self, code, body=b"", ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def target(self, prefix):
        f = unquote(urlparse(self.path).path[len(prefix):])
        p = os.path.join(DIR, f)
        return (f, p) if SAFE.match(f) and not f.endswith(".json") and os.path.isfile(p) else (None, None)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fh:
                return self.send(200, fh.read(), "text/html; charset=utf-8")
        if path == "/api/files":
            return self.send(200, listing())
        if path.startswith("/files/"):
            return self.serve_file()
        self.send(404, {"error": "not found"})

    do_HEAD = do_GET

    def serve_file(self):
        f, p = self.target("/files/")
        if not f:
            return self.send(404, {"error": "not found"})
        size = os.path.getsize(p)
        ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else end
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
        partial = (start, end) != (0, size - 1)
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(p, "rb") as fh:
            fh.seek(start); left = end - start + 1
            while left > 0:
                chunk = fh.read(min(65536, left))
                if not chunk:
                    break
                self.wfile.write(chunk); left -= len(chunk)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/upload":
            return self.send(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length", 0))
        if not 0 < n <= MAX_BYTES:
            return self.send(413, {"error": "empty or too large"})
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        ctype = self.headers.get("Content-Type", "").split(";")[0].strip()
        orig = q.get("filename", "")
        ext = EXT.get(ctype) or (os.path.splitext(orig)[1].lower() if re.match(r"^\.\w{2,5}$", os.path.splitext(orig)[1]) else ".bin")
        name = q.get("name") or os.path.splitext(orig)[0] or "recording"
        now = datetime.now(TZ)
        f = f"{now:%Y-%m-%d_%H-%M-%S}_{slug(name) or 'recording'}{ext}"
        data = self.rfile.read(n)
        with open(os.path.join(DIR, f), "wb") as fh:
            fh.write(data)
        dur = q.get("duration")
        with open(meta_path(f), "w") as fh:
            json.dump({"name": name, "created": now.isoformat(timespec="seconds"), "mime": ctype,
                       "duration": float(dur) if dur else None, "source": q.get("source", "file")}, fh)
        self.send(201, {"file": f})

    def do_DELETE(self):
        f, p = self.target("/api/files/")
        if not f:
            return self.send(404, {"error": "not found"})
        os.remove(p)
        if os.path.exists(meta_path(f)):
            os.remove(meta_path(f))
        self.send(200, {"deleted": f})


if __name__ == "__main__":
    os.makedirs(DIR, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
