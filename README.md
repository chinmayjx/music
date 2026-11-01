# music

Phone page for recording hums and ideas straight into the devbox, as the first step of hum-to-music production.

- `server.py`: stdlib Python server on `127.0.0.1:8792` (systemd `music-recorder`), exposed on the tailnet at `https://claude-devbox.tail0e5368.ts.net:8459`
- Recordings go to `~/data/music/recordings`, each with a `.json` sidecar (name, created, duration, mime, source)
- The mic is captured with noise suppression and auto-gain off, so pitch tracking gets the raw voice

## studio (the music service)

Runs on the Lenovo (Pop!_OS, x86, Surge XT) at `https://lenovo.tail0e5368.ts.net`, tailnet only. Deploy with `studio/deploy.sh`.

- `GET /instruments`: Surge XT factory patches by category, plus builtins (`hat`, `open-hat`)
- `POST /render?format=mp3|wav`: a song spec (tempo + tracks of notes; see `studio/engine.py`) -> audio, cached by spec (`X-Render-Id`, `GET /renders/<id>.mp3`)
- `POST /transcribe`: multipart `file` (any audio), `scale=true|false`, optional `bpm` -> notes and key

Layout: `studio/` is the service and the shared code (Surge loading, pitch tracking); `produce/` holds the devbox-side scripts and `laptop/` the one-off track scripts from the first experiments.
