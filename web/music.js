/* music.js: web components for music input and playback in artifacts. No dependencies.
 *
 *   <script src="https://cdn.jsdelivr.net/gh/chinmayjx/music@<tag>/web/music.js"></script>
 *
 *   <music-keyboard start="C4" octaves="2" bpm="100" sound="epiano" count-in="1" save-to="takes"></music-keyboard>
 *     start      lowest key (default C4)          octaves   how many octaves (default 2)
 *     bpm        tempo for the metronome and beats (default 100)
 *     sound      epiano | synth | organ | pluck | bell (default epiano)
 *     count-in   bars of clicks before recording starts (default 1; 0 for none)
 *     metronome  "off" to record without clicks   quantize  1/n of a beat to snap beats to (e.g. 4), stored alongside
 *     save-to    a hub collection: each take is saved there (needs the artifact hub's window.hub)
 *     events: noteon / noteoff {pitch, velocity}, take {take}, saved {record}
 *     a take: {bpm, sound, duration, device, created, notes: [{pitch, name, vel, start, dur, start_beat, dur_beats}]}
 *
 *   <music-roll></music-roll>      roll.take = take  (or roll.notes / roll.bpm): a piano roll with a play button
 *
 *   <music-recorder save-to="recordings" processing="off"></music-recorder>
 *     records the microphone; processing "off" (default: raw voice, best for humming and pitch) or "on" (the
 *     browser's noise suppression, echo cancellation and auto gain). With save-to, the audio goes into the hub's
 *     file store and a record {file_id, name, mime, size, duration, note, created} into that collection; the
 *     component's note field fills `note`. events: recording {blob, duration}, saved {record}
 *
 *   Music.play(notes, {bpm, sound, from})    notes in beats ({pitch, start_beat, dur_beats}) or seconds ({start, dur});
 *                                            starts at the first note's beat unless `from` (a beat) is given
 *   Music.render(spec, {studio})             a studio render (POST /render) -> Blob (mp3)
 *   Music.noteName(60) -> "C4", Music.midi("C#4") -> 61
 */
(() => {
  if (window.Music) return;
  const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const STUDIO = "https://lenovo.tail0e5368.ts.net";
  const noteName = (m) => NAMES[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1);
  const midi = (s) => {
    if (typeof s === "number") return s;
    const m = /^([A-Ga-g])([#b]?)(-?\d)$/.exec(String(s).trim());
    if (!m) throw new Error("bad note " + s);
    const base = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }[m[1].toUpperCase()];
    return base + (m[2] === "#" ? 1 : m[2] === "b" ? -1 : 0) + 12 * (+m[3] + 1);
  };
  const hz = (m) => 440 * Math.pow(2, (m - 69) / 12);

  // ---- sound: one shared AudioContext, small synth voices ------------------------------------------------
  let ctx = null, out = null;
  function audio() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      const comp = ctx.createDynamicsCompressor();
      out = ctx.createGain(); out.gain.value = 0.5;
      out.connect(comp); comp.connect(ctx.destination);
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  const SOUNDS = {
    epiano(c, f, t, v) {   // two-operator FM, like a Rhodes
      const car = c.createOscillator(), mod = c.createOscillator(), mg = c.createGain(), g = c.createGain();
      car.frequency.value = f; mod.frequency.value = f; mod.connect(mg); mg.connect(car.frequency);
      mg.gain.setValueAtTime(f * 1.6 * v, t); mg.gain.exponentialRampToValueAtTime(f * 0.15, t + 1.2);
      env(g, t, v * 0.6, 0.004, 2.2, 0.25); car.connect(g);
      return voice([car, mod], g, 0.35, t);
    },
    synth(c, f, t, v) {     // saw through a closing low-pass
      const o = c.createOscillator(), o2 = c.createOscillator(), fl = c.createBiquadFilter(), g = c.createGain();
      o.type = o2.type = "sawtooth"; o.frequency.value = f; o2.frequency.value = f * 1.004;
      fl.type = "lowpass"; fl.Q.value = 4; fl.frequency.setValueAtTime(Math.min(f * 10, 12000), t);
      fl.frequency.exponentialRampToValueAtTime(Math.max(f * 2, 300), t + 0.6);
      env(g, t, v * 0.25, 0.01, 6, 0.7); o.connect(fl); o2.connect(fl); fl.connect(g);
      return voice([o, o2], g, 0.25, t);
    },
    organ(c, f, t, v) {
      const g = c.createGain(), oscs = [1, 2, 3, 4].map((h, i) => {
        const o = c.createOscillator(), og = c.createGain(); o.frequency.value = f * h; og.gain.value = [1, .5, .3, .2][i];
        o.connect(og); og.connect(g); return o;
      });
      env(g, t, v * 0.18, 0.01, 60, 1); return voice(oscs, g, 0.08, t);
    },
    pluck(c, f, t, v) {
      const o = c.createOscillator(), fl = c.createBiquadFilter(), g = c.createGain();
      o.type = "triangle"; o.frequency.value = f; fl.type = "lowpass"; fl.frequency.setValueAtTime(f * 8, t);
      fl.frequency.exponentialRampToValueAtTime(f * 1.5, t + 0.3);
      env(g, t, v * 0.5, 0.002, 0.9, 0.05); o.connect(fl); fl.connect(g); return voice([o], g, 0.15, t);
    },
    bell(c, f, t, v) {
      const car = c.createOscillator(), mod = c.createOscillator(), mg = c.createGain(), g = c.createGain();
      car.frequency.value = f; mod.frequency.value = f * 3.5; mod.connect(mg); mg.connect(car.frequency);
      mg.gain.setValueAtTime(f * 2 * v, t); mg.gain.exponentialRampToValueAtTime(f * 0.05, t + 2.5);
      env(g, t, v * 0.4, 0.002, 3.5, 0.05); car.connect(g); return voice([car, mod], g, 0.6, t);
    },
  };
  // attack to peak, then exponential decay toward `sustain`×peak over `decay` seconds
  function env(g, t, peak, attack, decay, sustain) {
    g.gain.value = 0;                       // silent until its start time (a gain node's default is 1)
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(Math.max(peak, 0.001), t + attack);
    g.gain.setTargetAtTime(Math.max(peak * sustain, 0.0001), t + attack, decay / 3);
  }
  function voice(oscs, g, release, at) {
    g.connect(out); oscs.forEach((o) => o.start(at));
    return {
      stop(when) {
        const t = Math.max(when || 0, ctx.currentTime);
        // hold the level reached at t, then fade; cancelling without holding jumps the level and clicks
        if (g.gain.cancelAndHoldAtTime) g.gain.cancelAndHoldAtTime(t); else g.gain.cancelScheduledValues(t);
        g.gain.setTargetAtTime(0.0001, t, release / 3);
        oscs.forEach((o) => o.stop(t + release * 3));
      },
    };
  }
  function noteOn(pitch, vel = 0.8, sound = "epiano", at) {
    const c = audio();
    return (SOUNDS[sound] || SOUNDS.epiano)(c, hz(pitch), at || c.currentTime, vel);
  }
  function click(accent, at) {
    const c = audio(), o = c.createOscillator(), g = c.createGain();
    o.frequency.value = accent ? 1600 : 1000;
    g.gain.setValueAtTime(accent ? 0.5 : 0.3, at); g.gain.exponentialRampToValueAtTime(0.0001, at + 0.05);
    o.connect(g); g.connect(out); o.start(at); o.stop(at + 0.06);
  }

  // Where playback and the roll begin: the beat of the first note, so silence before it (a pause after
  // tapping Record) isn't played, while notes keep their place relative to the beat.
  const startOf = (n, spb) => (n.start_beat != null ? n.start_beat * spb : n.start || 0);
  function firstBeat(notes, spb) {
    return notes.length ? Math.floor(Math.min(...notes.map((n) => startOf(n, spb))) / spb + 1e-6) : 0;
  }

  // Play notes; returns {stop(), done: Promise}. from: the beat to start at (default: the first note's beat).
  function play(notes, { bpm = 100, sound = "epiano", from } = {}) {
    const c = audio(), t0 = c.currentTime + 0.05, spb = 60 / bpm;
    const skip = (from ?? firstBeat(notes, spb)) * spb;
    let end = 0;
    const voices = notes.map((n) => {
      const start = startOf(n, spb) - skip;
      const dur = n.dur_beats != null ? n.dur_beats * spb : n.dur || spb;
      end = Math.max(end, start + dur);
      const v = noteOn(midi(n.pitch), (n.vel || 100) / 127, sound, t0 + start);
      v.stop(t0 + start + dur);
      return v;
    });
    let timer;
    const done = new Promise((r) => (timer = setTimeout(r, (end + 0.5) * 1000)));
    return { done, stop() { clearTimeout(timer); voices.forEach((v) => v.stop()); } };
  }

  async function render(spec, { studio = STUDIO, format = "mp3" } = {}) {
    const r = await fetch(`${studio}/render?format=${format}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(spec),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "render failed: " + r.status);
    return r.blob();
  }

  const THEME = `
    :host{--bg:#fff;--fg:#1f1e1d;--muted:#6b6a66;--line:#d8d5cc;--card:#f4f2ec;--accent:#d97757;--white:#fdfcf9;--black:#2b2a27;--on:#d97757;
      display:block;font:14px/1.3 system-ui,sans-serif;color:var(--fg);-webkit-tap-highlight-color:transparent;user-select:none}
    @media(prefers-color-scheme:dark){:host{--bg:#1f1e1d;--fg:#f0eee6;--muted:#a3a19a;--line:#3a3935;--card:#2b2a27;--white:#e9e6dc;--black:#141413}}
    button,input{font:inherit;color:inherit}
    .btn{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:7px 11px;min-height:36px;cursor:pointer}
    .btn.rec{background:var(--accent);border-color:var(--accent);color:#fff}
    .btn:disabled{opacity:.4}
  `;

  // ---- <music-keyboard> ---------------------------------------------------------------------------------
  class MusicKeyboard extends HTMLElement {
    static get observedAttributes() { return ["start", "octaves", "bpm", "sound"]; }
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this.held = new Map();      // pointer id / "midi:<n>" -> {pitch, voice, t}
      this.recording = null;      // {t0, notes, open: Map}
      this.take = null;
    }
    get bpm() { return +this.getAttribute("bpm") || 100; }
    set bpm(v) { this.setAttribute("bpm", v); }
    get sound() { return this.getAttribute("sound") || "epiano"; }
    connectedCallback() { this.renderUI(); }
    attributeChangedCallback() { if (this.shadowRoot.firstChild) this.renderUI(); }

    renderUI() {
      const start = midi(this.getAttribute("start") || "C4") + (this.shift || 0);
      const octaves = Math.max(1, Math.min(5, +this.getAttribute("octaves") || 2));
      const keys = []; for (let m = start; m <= start + 12 * octaves; m++) keys.push(m);
      const whites = keys.filter((m) => !NAMES[m % 12].includes("#"));
      const W = 100 / whites.length;
      let wi = 0;
      const keyHtml = keys.map((m) => {
        const black = NAMES[m % 12].includes("#");
        if (!black) { wi++; return `<div class="k w" data-p="${m}" style="left:${(wi - 1) * W}%;width:${W}%"><span>${m % 12 === 0 ? noteName(m) : ""}</span></div>`; }
        return `<div class="k b" data-p="${m}" style="left:${wi * W - W * 0.3}%;width:${W * 0.6}%"></div>`;
      }).join("");
      this.shadowRoot.innerHTML = `<style>${THEME}
        .bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px}
        .bpm{display:flex;align-items:center;gap:4px}.bpm input{width:52px;text-align:center;padding:6px;border:1px solid var(--line);border-radius:8px;background:var(--bg)}
        .status{flex:1 1 100%;color:var(--muted);font-size:13px;min-height:17px}
        .keys{position:relative;height:var(--key-height,170px);touch-action:none;border-radius:8px;overflow:hidden;background:var(--black)}
        .k{position:absolute;top:0;box-sizing:border-box}
        .w{height:100%;background:var(--white);border:1px solid var(--line);border-radius:0 0 6px 6px;display:flex;align-items:flex-end;justify-content:center}
        .w span{font-size:10px;color:#888;padding-bottom:4px}
        .b{height:60%;background:var(--black);border-radius:0 0 4px 4px;z-index:1;border:1px solid #000}
        .k.on{background:var(--on)!important}
      </style>
      <div class="bar">
        <button class="btn" data-a="down" aria-label="Octave down">◀</button><button class="btn" data-a="up" aria-label="Octave up">▶</button>
        <span class="bpm"><button class="btn" data-a="slower">−</button><input type="number" min="30" max="300" value="${this.bpm}" aria-label="BPM"><button class="btn" data-a="faster">+</button> BPM</span>
        <button class="btn" data-a="metro">${this.getAttribute("metronome") === "off" ? "Click off" : "Click on"}</button>
        <button class="btn" data-a="midi">MIDI</button>
        <button class="btn rec" data-a="rec">● Record</button>
        <button class="btn" data-a="play" ${this.take ? "" : "disabled"}>▶ Play</button>
        <div class="status"></div>
      </div>
      <div class="keys">${keyHtml}</div>`;
      this.$ = (s) => this.shadowRoot.querySelector(s);
      this.wire();
    }

    status(t) { this.$(".status").textContent = t; }

    wire() {
      const kb = this.$(".keys");
      const keyAt = (x, y) => { const el = this.shadowRoot.elementFromPoint(x, y); return el && el.closest && el.closest(".k"); };
      kb.addEventListener("pointerdown", (e) => {
        e.preventDefault(); kb.setPointerCapture(e.pointerId);
        const k = keyAt(e.clientX, e.clientY); if (k) this.press(e.pointerId, +k.dataset.p, e.pressure && e.pointerType === "pen" ? e.pressure : 0.8);
      });
      kb.addEventListener("pointermove", (e) => {
        if (!this.held.has(e.pointerId)) return;
        const k = keyAt(e.clientX, e.clientY);
        if (k && +k.dataset.p !== this.held.get(e.pointerId).pitch) { this.release(e.pointerId); this.press(e.pointerId, +k.dataset.p, 0.8); }
      });
      const up = (e) => this.release(e.pointerId);
      kb.addEventListener("pointerup", up); kb.addEventListener("pointercancel", up);
      this.shadowRoot.querySelector(".bar").addEventListener("click", (e) => {
        const a = e.target.closest("[data-a]"); if (!a) return;
        const act = a.dataset.a;
        if (act === "up" || act === "down") { this.shift = (this.shift || 0) + (act === "up" ? 12 : -12); this.renderUI(); }
        if (act === "faster" || act === "slower") this.bpm = Math.max(30, Math.min(300, this.bpm + (act === "faster" ? 5 : -5)));
        if (act === "metro") this.setAttribute("metronome", this.getAttribute("metronome") === "off" ? "on" : "off");
        if (act === "rec") this.recording ? this.stop() : this.record();
        if (act === "play" && this.take) this.playTake();
        if (act === "midi") this.connectMidi();
        if (["metro", "faster", "slower"].includes(act)) this.renderUI();
      });
      this.$(".bpm input").addEventListener("change", (e) => (this.bpm = Math.max(30, Math.min(300, +e.target.value || 100))));
    }

    press(id, pitch, vel, device = "touch") {
      const voice = noteOn(pitch, vel, this.sound);
      this.held.set(id, { pitch, voice, t: audio().currentTime, vel, device });
      const k = this.$(`.k[data-p="${pitch}"]`); if (k) k.classList.add("on");
      this.dispatchEvent(new CustomEvent("noteon", { detail: { pitch, velocity: Math.round(vel * 127) } }));
    }
    release(id) {
      const h = this.held.get(id); if (!h) return;
      this.held.delete(id); h.voice.stop();
      if (![...this.held.values()].some((x) => x.pitch === h.pitch)) { const k = this.$(`.k[data-p="${h.pitch}"]`); if (k) k.classList.remove("on"); }
      if (this.recording && h.t >= this.recording.t0 - 0.25) {   // notes just before the downbeat count as on it
        const start = Math.max(0, h.t - this.recording.t0), dur = Math.max(0.03, audio().currentTime - h.t);
        this.recording.notes.push({ pitch: h.pitch, vel: Math.round(h.vel * 127), start, dur, device: h.device });
      }
      this.dispatchEvent(new CustomEvent("noteoff", { detail: { pitch: h.pitch } }));
    }

    record() {
      const c = audio(), spb = 60 / this.bpm, bars = Math.max(0, +(this.getAttribute("count-in") ?? 1));
      const t0 = c.currentTime + 0.1 + bars * 4 * spb;
      this.recording = { t0, notes: [] };
      const metro = this.getAttribute("metronome") !== "off";
      for (let i = 0; i < bars * 4; i++) click(i % 4 === 0, c.currentTime + 0.1 + i * spb);
      // keep the click going while recording, scheduled a little ahead
      let beat = 0;
      const tick = () => {
        if (!this.recording) return;
        while (metro && t0 + beat * spb < c.currentTime + 0.3) { click(beat % 4 === 0, t0 + beat * spb); beat++; }
        if (!metro) beat = Math.ceil((c.currentTime - t0) / spb);
        this.status(c.currentTime < t0 ? `Count-in… ${Math.ceil((t0 - c.currentTime) / spb)}` : `Recording · bar ${Math.floor(Math.max(0, c.currentTime - t0) / spb / 4) + 1}`);
        this.timer = setTimeout(tick, 50);
      };
      tick();
      const b = this.$('[data-a="rec"]'); b.textContent = "■ Stop";
    }

    async stop() {
      clearTimeout(this.timer);
      [...this.held.keys()].forEach((id) => this.release(id));
      const rec = this.recording; this.recording = null;
      const b = this.$('[data-a="rec"]'); b.textContent = "● Record";
      if (!rec.notes.length) return this.status("Nothing played.");
      const spb = 60 / this.bpm, q = +this.getAttribute("quantize") || 0;
      const r3 = (x) => Math.round(x * 1000) / 1000;
      const snap = (x) => (q ? Math.round(x * q) / q : r3(x));
      const notes = rec.notes.sort((a, b) => a.start - b.start).map((n) => ({
        pitch: n.pitch, name: noteName(n.pitch), vel: n.vel, start: r3(n.start), dur: r3(n.dur),
        start_beat: snap(n.start / spb), dur_beats: Math.max(q ? 1 / q : 0.01, snap(n.dur / spb)),
      }));
      const take = {
        bpm: this.bpm, sound: this.sound, quantize: q || null, created: new Date().toISOString(),
        device: rec.notes.some((n) => n.device === "midi") ? "midi" : "touch",
        duration: r3(Math.max(...notes.map((n) => n.start + n.dur))), notes,
      };
      this.take = take;
      this.$('[data-a="play"]').disabled = false;
      this.status(`${notes.length} notes · ${take.duration.toFixed(1)} s`);
      this.dispatchEvent(new CustomEvent("take", { detail: { take } }));
      const to = this.getAttribute("save-to");
      if (to && window.hub) {
        try {
          const record = await window.hub.db.collection(to).add(take);
          this.status(`${notes.length} notes · saved ✓`);
          this.dispatchEvent(new CustomEvent("saved", { detail: { record } }));
        } catch (err) { this.status("Couldn't save: " + err.message); }
      }
    }

    playTake() { if (this.player) this.player.stop(); this.player = play(this.take.notes, { bpm: this.take.bpm, sound: this.sound }); }

    async connectMidi() {
      if (!navigator.requestMIDIAccess) return this.status("This browser has no Web MIDI. Use Chrome on Android or desktop.");
      try {
        const access = await navigator.requestMIDIAccess();
        const inputs = [...access.inputs.values()];
        if (!inputs.length) return this.status("No MIDI keyboard found. Plug it in (USB OTG on a phone) and tap MIDI again.");
        inputs.forEach((inp) => (inp.onmidimessage = (m) => {
          const [st, note, vel] = m.data, cmd = st & 0xf0;
          if (cmd === 0x90 && vel > 0) this.press("midi:" + note, note, vel / 127, "midi");
          else if (cmd === 0x80 || (cmd === 0x90 && vel === 0)) this.release("midi:" + note);
        }));
        this.status("MIDI: " + inputs.map((i) => i.name).join(", "));
      } catch (err) { this.status("MIDI not allowed here: " + err.message); }
    }
  }

  // ---- <music-roll> ---------------------------------------------------------------------------------------
  class MusicRoll extends HTMLElement {
    constructor() { super(); this.attachShadow({ mode: "open" }); this._notes = []; this._bpm = 100; }
    set take(t) { this._take = t; this._notes = t.notes || []; this._bpm = t.bpm || 100; this.draw(); }
    get take() { return this._take; }
    set notes(n) { this._notes = n || []; this.draw(); }
    set bpm(b) { this._bpm = +b || 100; this.draw(); }
    connectedCallback() { this.draw(); }
    draw() {
      const ns = this._notes, spb = 60 / this._bpm;
      const beats = (n) => [n.start_beat != null ? n.start_beat : (n.start || 0) / spb, n.dur_beats != null ? n.dur_beats : (n.dur || spb) / spb];
      const lo = ns.length ? Math.min(...ns.map((n) => midi(n.pitch))) - 1 : 59, hi = ns.length ? Math.max(...ns.map((n) => midi(n.pitch))) + 1 : 72;
      const from = firstBeat(ns, spb);
      const len = Math.max(4, Math.ceil(Math.max(0, ...ns.map((n) => beats(n).reduce((a, b) => a + b) - from)) / 4) * 4);
      const rows = hi - lo + 1, H = Math.max(80, Math.min(220, rows * 10)), rh = H / rows;
      const grid = Array.from({ length: len + 1 }, (_, b) => `<line x1="${(b / len) * 100}%" x2="${(b / len) * 100}%" y1="0" y2="${H}" stroke="var(--line)" stroke-width="${(b + from) % 4 ? 0.5 : 1.5}"/>`).join("");
      const lanes = Array.from({ length: rows }, (_, i) => NAMES[(hi - i) % 12].includes("#") ? `<rect x="0" width="100%" y="${i * rh}" height="${rh}" fill="var(--card)"/>` : "").join("");
      const bars = ns.map((n) => { const [s, d] = beats(n), p = midi(n.pitch);
        return `<rect x="${((s - from) / len) * 100}%" width="${Math.max(0.4, (d / len) * 100)}%" y="${(hi - p) * rh + 1}" height="${rh - 2}" rx="2" fill="var(--accent)"><title>${noteName(p)}</title></rect>`; }).join("");
      this.shadowRoot.innerHTML = `<style>${THEME}.wrap{display:flex;gap:8px;align-items:flex-start}svg{flex:1;min-width:0;width:100%;background:var(--bg);border:1px solid var(--line);border-radius:8px}
        .names{font-size:11px;color:var(--muted)}</style>
        <div class="wrap"><button class="btn" aria-label="Play">▶</button>
        <svg height="${H}" preserveAspectRatio="none">${lanes}${grid}${bars}</svg></div>
        <div class="names">${ns.map((n) => noteName(midi(n.pitch))).join(" ")}</div>`;
      this.shadowRoot.querySelector("button").onclick = () => {
        if (this.player) this.player.stop();
        this.player = play(ns, { bpm: this._bpm, sound: (this._take && this._take.sound) || "epiano" });
      };
    }
  }

  // ---- <music-recorder> -----------------------------------------------------------------------------------
  class MusicRecorder extends HTMLElement {
    constructor() { super(); this.attachShadow({ mode: "open" }); }
    connectedCallback() {
      this.shadowRoot.innerHTML = `<style>${THEME}
        .row{display:flex;gap:10px;align-items:center}
        .rec{width:64px;height:64px;border-radius:50%;border:3px solid var(--line);background:var(--card);display:grid;place-items:center;cursor:pointer;flex:none}
        .rec i{width:28px;height:28px;border-radius:50%;background:var(--accent);transition:all .15s}
        .rec.on{border-color:var(--accent)} .rec.on i{width:22px;height:22px;border-radius:5px}
        .side{flex:1;min-width:0;display:flex;flex-direction:column;gap:6px}
        .time{font:600 22px/1 ui-monospace,monospace;font-variant-numeric:tabular-nums}
        .meter{height:6px;border-radius:3px;background:var(--line);overflow:hidden}.meter b{display:block;height:100%;width:0;background:#4cc38a}
        input{width:100%;box-sizing:border-box;margin-top:10px;padding:9px 10px;border-radius:10px;border:1px solid var(--line);background:var(--bg)}
        .status{color:var(--muted);font-size:13px;min-height:17px;margin-top:6px}</style>
        <div class="row"><button class="rec" aria-label="Record"><i></i></button>
          <div class="side"><div class="time">0:00</div><div class="meter"><b></b></div></div></div>
        <input class="note" placeholder="What is this? (optional)" autocomplete="off">
        <div class="status">Tap to record</div>`;
      this.$ = (q) => this.shadowRoot.querySelector(q);
      this.$(".rec").onclick = () => (this.rec && this.rec.state === "recording" ? this.stop() : this.start());
    }
    status(t) { this.$(".status").textContent = t; }
    async start() {
      const on = this.getAttribute("processing") === "on";
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: on, noiseSuppression: on, autoGainControl: on } });
      } catch (err) {
        return this.status(err.name === "NotAllowedError"
          ? "Microphone not allowed. If Android just asked, allow it and tap Record again."
          : "Microphone unavailable: " + err.message);
      }
      const types = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"];
      const mime = types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
      this.chunks = [];
      this.rec = new MediaRecorder(this.stream, mime ? { mimeType: mime } : undefined);
      this.rec.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
      this.rec.onstop = () => this.finish();
      this.rec.start(1000);
      this.t0 = Date.now();
      this.$(".rec").classList.add("on"); this.status("Recording… tap to stop");
      const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
      this.tick = setInterval(() => (this.$(".time").textContent = fmt((Date.now() - this.t0) / 1000)), 250);
      const c = audio(), an = c.createAnalyser(); an.fftSize = 1024;
      this.src = c.createMediaStreamSource(this.stream); this.src.connect(an);
      const buf = new Float32Array(an.fftSize);
      const loop = () => { an.getFloatTimeDomainData(buf);
        this.$(".meter b").style.width = Math.min(100, Math.sqrt(buf.reduce((a, v) => a + v * v, 0) / buf.length) * 400) + "%";
        this.raf = requestAnimationFrame(loop); };
      loop();
    }
    stop() {
      this.rec.stop(); this.stream.getTracks().forEach((t) => t.stop());
      clearInterval(this.tick); cancelAnimationFrame(this.raf); this.src && this.src.disconnect();
      this.$(".meter b").style.width = 0; this.$(".rec").classList.remove("on");
    }
    async finish() {
      const duration = Math.round((Date.now() - this.t0) / 100) / 10;
      const type = (this.rec.mimeType || "audio/webm").split(";")[0];
      const blob = new Blob(this.chunks, { type });
      this.dispatchEvent(new CustomEvent("recording", { detail: { blob, duration } }));
      const to = this.getAttribute("save-to");
      if (!to) return this.status(`Recorded ${duration} s`);
      if (!window.hub) return this.status("Not saved: open this in the artifact hub.");
      const note = this.$(".note").value.trim();
      const stamp = new Date().toISOString();
      const name = `${stamp.slice(0, 19).replace(/[:T]/g, "-")}.${type.includes("mp4") ? "m4a" : type.split("/")[1]}`;
      try {
        this.status("Saving…");
        const f = await window.hub.files.put(blob, name);
        const record = await window.hub.db.collection(to).add({ file_id: f.id, name, mime: type, size: f.size, duration, note, created: stamp });
        this.$(".note").value = ""; this.$(".time").textContent = "0:00";
        this.status(`Saved ✓ ${duration} s`);
        this.dispatchEvent(new CustomEvent("saved", { detail: { record } }));
      } catch (err) { this.status("Couldn't save: " + err.message); }
    }
  }

  customElements.define("music-keyboard", MusicKeyboard);
  customElements.define("music-roll", MusicRoll);
  customElements.define("music-recorder", MusicRecorder);
  window.Music = { play, render, noteOn, noteName, midi, sounds: Object.keys(SOUNDS), studio: STUDIO,
    output: () => (audio(), out) };   // the master bus, for meters or recording
})();
