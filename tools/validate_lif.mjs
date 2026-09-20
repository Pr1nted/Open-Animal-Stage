// Does the browser core produce EXACTLY the spikes the reference does?
//
//   node tools/validate_lif.mjs data/lif_reference.json
//
// Exact, not approximately. A browser brain that fires "about as often" as the
// reference is not the same model, and the difference would compound over a
// game of a hundred turns into a different animal. Open Fly's bar is spike for
// spike against Brian2; this is the same bar against lif.py.
import { readFileSync } from "node:fs";
import { Brain } from "../web/lif.js";

const ref = JSON.parse(readFileSync(process.argv[2] || "data/lif_reference.json", "utf8"));
const spec = {
  neurons: ref.neurons.map(sign => ({ sign })),
  synapses: ref.synapses,
  sensory: ref.sensory,
};
const brain = new Brain(spec, ref.params);

let firstBad = null;
let total = 0;
for (let w = 0; w < ref.schedule.length; w++) {
  for (const [ch, amt] of Object.entries(ref.schedule[w])) {
    brain.stimulate(spec.sensory[ch], amt);
  }
  const got = brain.run(ref.window_ms);
  const want = ref.windows[w];
  for (const v of got.values()) total += v;

  // Every neuron either side, so a spike the port invented is caught as well
  // as one it missed.
  // Membrane potentials first, and EXACTLY. A spike match with a drifted
  // membrane is a port that is wrong in a way that has not shown up yet.
  if (ref.potentials && firstBad === null) {
    const wantV = ref.potentials[w];
    for (let i = 0; i < wantV.length; i++) {
      if (brain.v[i] !== wantV[i]) {
        firstBad = { window: w, neuron: i, reference: wantV[i],
                     browser: brain.v[i], what: "membrane potential" };
        break;
      }
    }
  }

  const ids = new Set([...Object.keys(want).map(Number), ...got.keys()]);
  for (const i of ids) {
    const a = want[String(i)] || 0;
    const b = got.get(i) || 0;
    if (a !== b && firstBad === null) {
      firstBad = { window: w, neuron: i, reference: a, browser: b, what: "spike count" };
    }
  }
}

if (firstBad) {
  console.log(`  FAIL  ${firstBad.what} diverges at window ${firstBad.window}, ` +
              `neuron ${firstBad.neuron}: reference ${firstBad.reference}, ` +
              `browser ${firstBad.browser}`);
  process.exit(1);
}
if (total !== ref.total_spikes) {
  console.log(`  FAIL  total spikes ${total} vs reference ${ref.total_spikes}`);
  process.exit(1);
}
console.log(`  ok    ${ref.neurons.length} neurons, ${ref.synapses.length} synapses, ` +
            `${ref.schedule.length} windows: ${total} spikes and every membrane potential ` +
            `bit-identical to the reference`);
