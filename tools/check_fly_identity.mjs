// The female fly on this stage must BE Open Fly's fly: web/brain.js is FlyBrain
// with gap junctions and a shuffle added, and neither may change a species that
// has neither. This runs both engines on the same connectome, the same rates
// and the same seed, and requires every neuron's spike count to agree.
//
//   node tools/check_fly_identity.mjs [path/to/Open-Fly]
//
// Two checks, because either alone passes a real break: Open Fly's own SFC1
// file through AnimalBrain (the engine), and this repo's OAS1 export through
// AnimalBrain (the export). Then a shuffled brain must NOT agree, or the
// control is not a control.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const fly = path.resolve(process.argv[2] || path.join(here, "..", "..", "Open-Fly"));
const { FlyBrain } = await import(path.join(fly, "web", "brain.js"));
const { AnimalBrain } = await import(path.join(here, "..", "web", "brain.js"));
const buf = (p) => { const b = readFileSync(p); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };

const metaFly = JSON.parse(readFileSync(path.join(fly, "web", "data", "brain.json"), "utf8"));
const sfc = buf(path.join(fly, "web", "data", "connectome.bin"));
const oasDir = path.join(here, "..", "web", "species", "drosophila_female");
const metaOas = JSON.parse(readFileSync(path.join(oasDir, "brain.json"), "utf8"));
const oas = buf(path.join(oasDir, "connectome.bin"));

const rates = { sugar: 180, bitter: 60, water: 120, jon: 90 };
const WINDOW = 200, SEEDS = [1, 20240922];
let failed = 0;
const same = (a, b) => { let d = 0, s = 0; for (let i = 0; i < a.length; i++) { s += a[i]; if (a[i] !== b[i]) d++; } return { d, s }; };
const report = (ok, what) => { if (!ok) failed++; console.log(`  ${ok ? "ok  " : "FAIL"}  ${what}`); };

for (const seed of SEEDS) {
  const ref = new FlyBrain(sfc, metaFly).runWindow(rates, WINDOW, seed);
  const a = new AnimalBrain(sfc, metaFly).runWindow(rates, WINDOW, seed);
  let r = same(ref, a);
  report(r.d === 0 && r.s > 0, `seed ${seed}: AnimalBrain on Open Fly's file: ${r.s} spikes, ${r.d} neurons differ`);
  const senses = metaOas.senses || {};
  const oasRates = {}; for (const ch of Object.keys(senses)) oasRates[ch] = rates[ch];
  const b = new AnimalBrain(oas, metaOas).runWindow(oasRates, WINDOW, seed);
  r = same(ref, b);
  report(r.d === 0, `seed ${seed}: AnimalBrain on this repo's export: ${r.d} neurons differ`);
  const sh = new AnimalBrain(oas, metaOas); sh.shuffle(783);
  r = same(ref, sh.runWindow(oasRates, WINDOW, seed));
  report(r.d > 0, `seed ${seed}: the shuffled control differs (${r.d} neurons), as a control must`);
}
const g = (m) => JSON.stringify(m.groups), mo = metaOas.motor || metaOas.dn;
report(g(metaFly) === g(metaOas), "the 39 action groups are Open Fly's, neuron for neuron");
report(JSON.stringify(metaFly.dn) === JSON.stringify(mo), "and so are the descending neurons read as the motor set");
console.log(failed ? `\n${failed} failed` : "\nALL PASSED");
process.exit(failed ? 1 : 0);
