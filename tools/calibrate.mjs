// The one free constant for the species with no published model, set by the
// rule in PREREGISTRATION.md ("The neuron, and how its one free constant is
// set") and by nothing else. No game is played here.
//
//   node tools/calibrate.mjs                  # measure and print
//   node tools/calibrate.mjs --write          # and record into each brain.json
//
// Measure: every sensory channel at 100 Hz for one 200 ms window, seeds 1..5;
// the fraction of the 39 action groups with at least one spike, averaged.
// Target: the female fly's value under the same drive. Ladder: w_syn = 0.275 *
// 2^k, k = 0..10; the smallest k reaching the target wins. w_gap = 1, fixed.
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { AnimalBrain } from "../web/brain.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const species = path.join(here, "..", "web", "species");
const CALIBRATED = ["drosophila_larva", "c_elegans_herm", "c_elegans_male", "ciona_larva", "zebrafish_larva"];
const SEEDS = [1, 2, 3, 4, 5], HZ = 100, WINDOW = 200, W0 = 0.275, KMAX = 10, W_GAP = 1;
const write = process.argv.includes("--write");

const load = (id) => {
  const meta = JSON.parse(readFileSync(path.join(species, id, "brain.json"), "utf8"));
  const b = readFileSync(path.join(species, id, "connectome.bin"));
  return { meta, buf: b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) };
};
function measure({ meta, buf }, params) {
  const m = { ...meta, params: { ...meta.params, ...params } };
  const rates = Object.fromEntries(Object.keys(meta.sensory).map((ch) => [ch, HZ]));
  const groups = Object.values(meta.groups).flat();
  let sum = 0;
  for (const seed of SEEDS) {
    const counts = new AnimalBrain(buf, m).runWindow(rates, WINDOW, seed);
    sum += groups.filter((g) => g.some((i) => counts[i] > 0)).length / groups.length;
  }
  return sum / SEEDS.length;
}

const fly = load("drosophila_female");
const target = measure(fly, {});
console.log(`target: the female fly's published model reaches ${(100 * target).toFixed(1)}% of its 39 groups`);
for (const id of CALIBRATED) {
  let pkg;
  try { pkg = load(id); } catch { console.log(`${id}: no package, skipped`); continue; }
  const ladder = [];
  let chosen = null;
  for (let k = 0; k <= KMAX; k++) {
    const v = measure(pkg, { w_syn: W0 * 2 ** k, w_gap: new AnimalBrain(pkg.buf, pkg.meta).ngap ? W_GAP : 0 });
    ladder.push([k, +v.toFixed(4)]);
    if (v >= target) { chosen = k; break; }
  }
  const reached = chosen !== null;
  const k = reached ? chosen : KMAX;
  console.log(`${id}: k = ${k}, w_syn = ${(W0 * 2 ** k).toFixed(3)}${reached ? "" : "  (NEVER REACHED THE TARGET)"}  ladder ${ladder.map(([a, b]) => `${a}:${(100 * b).toFixed(0)}%`).join(" ")}`);
  if (write) {
    const p = path.join(species, id, "brain.json");
    const meta = JSON.parse(readFileSync(p, "utf8"));
    meta.params.w_syn = W0 * 2 ** k;
    meta.params.w_gap = new AnimalBrain(pkg.buf, pkg.meta).ngap ? W_GAP : 0;
    meta.params.calibrated = { rule: "PREREGISTRATION.md: The neuron, and how its one free constant is set", target: +target.toFixed(4), k, reached, ladder, on: new Date().toISOString().slice(0, 10) };
    writeFileSync(p, JSON.stringify(meta));
  }
}
