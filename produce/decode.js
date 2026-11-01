// Decode any browser-playable audio file to mono 16-bit WAV using headless Chromium's WebAudio.
// usage: node decode.js <in> <out.wav> [sampleRate]
const fs = require('fs');
const { chromium } = require('playwright');
(async () => {
  const [inp, out, sr = '22050'] = process.argv.slice(2);
  const b64 = fs.readFileSync(inp).toString('base64');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const pcm = await page.evaluate(async ({ b64, sr }) => {
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const ctx = new OfflineAudioContext(1, 1, +sr);
    const buf = await ctx.decodeAudioData(bytes.buffer);
    const ch = buf.numberOfChannels, n = buf.length, mono = new Float32Array(n);
    for (let c = 0; c < ch; c++) { const d = buf.getChannelData(c); for (let i = 0; i < n; i++) mono[i] += d[i] / ch; }
    return Array.from(mono, v => Math.max(-32768, Math.min(32767, Math.round(v * 32767))));
  }, { b64, sr });
  await browser.close();
  const data = Buffer.alloc(pcm.length * 2); pcm.forEach((v, i) => data.writeInt16LE(v, i * 2));
  const h = Buffer.alloc(44), rate = +sr;
  h.write('RIFF', 0); h.writeUInt32LE(36 + data.length, 4); h.write('WAVEfmt ', 8); h.writeUInt32LE(16, 16);
  h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28);
  h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write('data', 36); h.writeUInt32LE(data.length, 40);
  fs.writeFileSync(out, Buffer.concat([h, data]));
  console.log(`${out}: ${(pcm.length / rate).toFixed(2)} s`);
})();
