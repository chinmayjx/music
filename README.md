# music

Phone page for recording hums and ideas straight into the devbox, as the first step of hum-to-music production.

- `server.py`: stdlib Python server on `127.0.0.1:8792` (systemd `music-recorder`), exposed on the tailnet at `https://claude-devbox.tail0e5368.ts.net:8459`
- Recordings go to `~/data/music/recordings`, each with a `.json` sidecar (name, created, duration, mime, source)
- The mic is captured with noise suppression and auto-gain off, so pitch tracking gets the raw voice
