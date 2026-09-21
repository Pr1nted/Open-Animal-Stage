// The mouse's visual cortex, off the page's thread: the MICrONS digital twin
// (Wang et al., Nature 2025; github.com/cajal/fnn, MIT) exported to ONNX by
// tools/export_microns_twin.py. See docs/mouse.md for what this does and does
// not claim. In one line: these are PREDICTIONS of what 8,221 recorded neurons
// of mouse 17797 would do if shown the map, from a model fitted to their
// recordings -- not a simulation of the wiring, and not a player.
//
// The mouse keeps looking: its recurrent state carries from one look to the
// next, so a new map is seen after the old one, as a real screen would be.
// Behaviour inputs are fnn's own default, 0 (average pupil, average running):
// there is no mouse here, so there is no behaviour to report.
const ORT = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/";
importScripts(ORT + "ort.webgpu.min.js");
// In a worker there is no <script> tag for the runtime to find its .wasm
// files beside, so it is told where they are.
ort.env.wasm.wasmPaths = ORT;

let sess = null, meta = null, state = null, looks = 0, ep = "";

// THE MODEL IN PARTS. At 36.6 MB it is over the 25 MiB a static host accepts
// per file, so a published build carries model.onnx.part.* and a manifest
// (tools/pack_web.py). The parts are joined and checked against the manifest's
// sha256 before the runtime sees a byte; a local build may have the whole file.
async function loadModel(base) {
  // A manifest only if it parses as one: a host may answer a missing file with
  // 200 and its index.html, and a content-type check trusts the host.
  let m = null;
  try { const man = await fetch(new URL("model.pack.json", base)); if (man.ok) { const j = JSON.parse(await man.text()); if (Array.isArray(j.parts)) m = j; } } catch { m = null; }
  if (m) {
    const parts = await Promise.all(m.parts.map(async (name) => {
      for (let attempt = 1; ; attempt++) {
        try { const r = await fetch(new URL(name, base)); if (!r.ok) throw new Error(`${name}: ${r.status}`); return new Uint8Array(await r.arrayBuffer()); }
        catch (err) { if (attempt >= 4) throw err; await new Promise((res) => setTimeout(res, 500 * attempt)); }
      }
    }));
    const whole = new Uint8Array(m.size); let off = 0;
    for (const p of parts) { whole.set(p, off); off += p.length; }
    if (off !== m.size) throw new Error(`model parts are ${off} bytes, the manifest says ${m.size}`);
    const hex = [...new Uint8Array(await crypto.subtle.digest("SHA-256", whole))].map((b) => b.toString(16).padStart(2, "0")).join("");
    if (hex !== m.sha256) throw new Error("model parts do not match the manifest's checksum");
    return whole.buffer;
  }
  const r = await fetch(new URL("model.onnx", base));
  if (!r.ok) throw new Error(`model.onnx answered ${r.status}`);
  return r.arrayBuffer();
}
const zeros2 = () => new ort.Tensor("float32", new Float32Array(2), [1, 2]);

self.onmessage = async (e) => {
  const msg = e.data;
  try {
    if (msg.type === "load") {
      meta = await (await fetch(new URL("mouse.json", new URL(msg.base, self.location.href)))).json();
      const buf = await loadModel(new URL(msg.base, self.location.href));
      const tried = [];
      for (const want of ["webgpu", "wasm"]) {
        try { sess = await ort.InferenceSession.create(buf, { executionProviders: [want] }); ep = want; break; }
        catch (err) { tried.push(`${want}: ${err && err.message || err}`); if (want === "wasm") throw new Error(tried.join("; ")); }
      }
      state = meta.state.map((s) => new ort.Tensor("float32", new Float32Array(s.shape.reduce((a, b) => a * b, 1)), s.shape));
      self.postMessage({ type: "loaded", meta, ep });
    } else if (msg.type === "look") {
      // `frames` frames of one still image; the first look also runs the
      // model's burn-in, which is settling and not a response.
      const t0 = performance.now();
      const stim = new ort.Tensor("float32", msg.frame, [1, 1, 144, 256]);
      const burn = looks === 0 ? meta.input.burnin_frames : 0;
      const mean = new Float32Array(meta.n);
      let counted = 0;
      for (let t = 0; t < burn + msg.frames; t++) {
        const feeds = { stimulus: stim, perspective: zeros2(), modulation: zeros2() };
        meta.state.forEach((s, i) => { feeds[s.input] = state[i]; });
        const out = await sess.run(feeds);
        state = meta.state.map((s) => out[s.output]);
        if (t >= burn) { const r = out.response.data; for (let u = 0; u < meta.n; u++) mean[u] += r[u]; counted++; }
      }
      for (let u = 0; u < meta.n; u++) mean[u] /= counted;
      looks++;
      self.postMessage({ type: "looked", id: msg.id, response: mean, ms: performance.now() - t0, ep }, [mean.buffer]);
    }
  } catch (err) {
    self.postMessage({ type: "error", id: msg.id, message: String(err && err.message || err) });
  }
};
