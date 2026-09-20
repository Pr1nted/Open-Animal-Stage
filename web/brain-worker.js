// One animal's brain, off the page's thread. The stage starts one of these per
// seat (docs/stage.md: a stage of four is four workers, so a fish's cost is its
// own problem and not the worm's), loads that species' package once, and then
// runs one decision window per request.
import { AnimalBrain } from "./brain.js";
import { loadPacked } from "./packed.js";

let brain = null;

async function fetchConnectome(base, meta) {
  // A package over the static host's 25 MiB limit ships in parts with a
  // manifest (tools/pack_web.py, as Open Fly); a small one ships whole.
  const manifest = new URL("connectome.pack.json", base);
  const head = await fetch(manifest, { method: "HEAD" }).catch(() => null);
  // A missing file can answer 200 with index.html on some hosts, so the type is
  // checked too rather than trusting the status alone.
  if (head && head.ok && (head.headers.get("content-type") || "").includes("json"))
    return loadPacked(manifest.href, (got, total) => self.postMessage({ type: "progress", got, total }));
  const r = await fetch(new URL("connectome.bin", base));
  if (!r.ok) throw new Error(`${meta.species}: connectome.bin answered ${r.status}`);
  return r.arrayBuffer();
}

self.onmessage = async (e) => {
  const msg = e.data;
  try {
    if (msg.type === "load") {
      const base = new URL(msg.base, self.location.href);
      const meta = await (await fetch(new URL("brain.json", base))).json();
      const connectome = await fetchConnectome(base, meta);
      brain = new AnimalBrain(connectome, meta);
      const shuffled = msg.shuffleSeed != null ? brain.shuffle(msg.shuffleSeed) : null;
      self.postMessage({ type: "loaded", n: brain.n, nsyn: brain.nsyn, ngap: brain.ngap, meta, shuffled });
    } else if (msg.type === "run") {
      const t0 = performance.now();
      const counts = brain.runWindow(msg.rates, msg.windowMs, msg.seed);
      self.postMessage({ type: "ran", id: msg.id, counts, ms: performance.now() - t0 }, [counts.buffer]);
    }
  } catch (err) {
    self.postMessage({ type: "error", id: msg.id, message: String(err && err.message || err) });
  }
};
