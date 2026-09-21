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
const zeros2 = () => new ort.Tensor("float32", new Float32Array(2), [1, 2]);

self.onmessage = async (e) => {
  const msg = e.data;
  try {
    if (msg.type === "load") {
      meta = await (await fetch(new URL("mouse.json", new URL(msg.base, self.location.href)))).json();
      const r = await fetch(new URL("model.onnx", new URL(msg.base, self.location.href)));
      if (!r.ok) throw new Error(`model.onnx answered ${r.status}`);
      const buf = await r.arrayBuffer();
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
