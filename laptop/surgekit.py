"""Headless Surge XT rendering: load factory patches, play notes, mix stems to an MP3."""
import os, subprocess, tempfile
import numpy as np, soundfile as sf, dawdreamer as daw
import juce_state

SR = 44100
SURGE = os.path.expanduser("~/.vst3/Surge XT.vst3")
PATCHES = os.path.expanduser("~/opt/surge-xt/share/surge-xt/patches_factory")
_init_xml = None


def _engine():
    return daw.RenderEngine(SR, 512)


def load_patch(engine, synth, patch):
    """patch: 'Basses/Mellow'. Surge applies a loaded state one load late, so load twice."""
    global _init_xml
    if _init_xml is None:
        f = tempfile.mktemp(suffix=".state"); synth.save_state(f)
        _init_xml = juce_state.read(f); os.remove(f)
    data = open(os.path.join(PATCHES, patch + ".fxp"), "rb").read()[60:]
    f = tempfile.mktemp(suffix=".state"); juce_state.write(f, _init_xml, data)
    for _ in range(2):
        synth.load_state(f); engine.render(0.05)
    os.remove(f)


def render(patch, notes, seconds):
    """notes: [(midi, velocity, start_sec, dur_sec)] -> stereo float array (2, n)."""
    e = _engine(); s = e.make_plugin_processor("surge", SURGE)
    e.load_graph([(s, [])]); e.render(0.1)
    load_patch(e, s, patch)
    s.clear_midi()
    for n, v, t, d in notes:
        s.add_midi_note(int(n), int(max(1, min(127, v))), float(t), float(d))
    e.render(seconds)
    return e.get_audio()


def rms(a):
    return float(np.sqrt((a ** 2).mean()) + 1e-9)


def mix(stems, path, lowpass_hz=None):
    """stems: [(audio, level_db)] — each stem normalised to equal loudness, then set to level_db."""
    n = max(a.shape[1] for a, _ in stems)
    out = np.zeros((2, n))
    for a, db in stems:
        out[:, :a.shape[1]] += a / rms(a) * 0.1 * 10 ** (db / 20)
    if lowpass_hz:
        from scipy.signal import butter, sosfilt
        out = sosfilt(butter(2, lowpass_hz, fs=SR, output="sos"), out, axis=1)
    out = np.tanh(out * 1.5) / 1.5                      # gentle saturation
    out *= 0.89 / np.abs(out).max()                     # peak at -1 dBFS
    wav = path.rsplit(".", 1)[0] + ".wav"
    sf.write(wav, out.T, SR)
    if path.endswith(".mp3"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-b:a", "192k", path], check=True)
    return path
