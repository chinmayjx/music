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

## web components (`web/music.js`)

For HTML artifacts; no dependencies. Load a tagged version from jsDelivr:

```html
<script src="https://cdn.jsdelivr.net/gh/chinmayjx/music@v0.1.0/web/music.js"></script>
<music-keyboard start="C4" octaves="2" bpm="100" count-in="1" save-to="takes"></music-keyboard>
```

- `<music-keyboard>`: multi-touch piano (slides between keys), metronome, count-in, recording, Web MIDI keyboards.
  Emits `take` with `{bpm, notes: [{pitch, name, vel, start, dur, start_beat, dur_beats}], ...}`; with `save-to` each
  take goes into that artifact hub collection. Attributes are documented at the top of `music.js`.
- `<music-roll>`: set `.take` to show a piano roll with a play button.
- `<music-recorder save-to="recordings">`: records the microphone (raw by default, for humming); saves the audio to the hub's file store and a record with its file id, duration and an optional note.
- `Music.play(notes, {bpm, sound})` plays in the browser (Web Audio); `Music.render(spec)` asks studio for a full render.

Tags are immutable on jsDelivr, so each artifact keeps working with the version it was made with. Examples: `web/examples/keyboard.html`, `web/examples/voice.html`.
