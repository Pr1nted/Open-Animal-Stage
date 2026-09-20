// The leaky integrate-and-fire core, for the browser.
//
// A PORT of open_animal_stage/lif.py, line for line where it can be, and checked
// against it spike for spike by tools/validate_lif.mjs. That is the same
// standard Open Fly holds itself to against the published Brian2 model: a
// browser implementation is only trusted once it produces the same spikes as
// the reference on the same network.
//
// Why a port rather than a shared implementation: the page cannot run Python,
// and a model that exists twice has to be proved to exist once. The validator
// is that proof, and it runs in the test suite, so the two cannot drift apart
// without a red build.
//
// Every numeric step mirrors the Python ORDER OF OPERATIONS, not just its
// formula. Floating point is not associative: `(v_rest - v + g)` and
// `(g + v_rest - v)` differ in the last bit on 22% of realistic operand pairs,
// measured.
//
// This comment used to go on to claim that such a difference would fail the
// exact comparison. It did not. Reordering that one expression left all 10,429
// spikes of the reference identical, because the drift never crossed a
// threshold at a different step in twelve windows -- the validator compared
// SPIKES, and sub-threshold drift is invisible to a spike count. It now
// compares every membrane potential bit for bit after every window, and the
// reordering is caught in window 0. So the order below is not superstition:
// changing it is a detected failure.

export const Sign = { EXCITATORY: 1, INHIBITORY: -1, UNKNOWN: 0 };

export function checkParams(p) {
  if (!(p.dt > 0)) throw new Error("dt must be positive");
  const smallest = Math.min(p.tau_m, p.tau_s);
  if (p.dt > smallest / 2) {
    throw new Error(`dt=${p.dt} is more than half the smallest time constant ` +
                    `(${smallest}). The result would be an artefact of the step size.`);
  }
  if (p.v_threshold <= p.v_rest) {
    throw new Error(`threshold ${p.v_threshold} is at or below rest ${p.v_rest}`);
  }
  if (p.t_refractory < 0 || p.t_delay < 0) {
    throw new Error("a refractory period or delay cannot be negative");
  }
  return true;
}

export class Brain {
  // spec: { neurons: [{sign}], synapses: [[pre, post, w]], sensory: {name: [ids]} }
  constructor(spec, params) {
    checkParams(params);
    this.spec = spec;
    this.p = params;
    const n = spec.neurons.length;
    this.n = n;

    // Outgoing edges with the sign folded in once, as in lif.py. An UNKNOWN
    // sign drops the edge: it is neither zero nor excitatory.
    this.out = Array.from({ length: n }, () => []);
    for (const [pre, post, w] of spec.synapses) {
      const s = spec.neurons[pre].sign;
      if (s === Sign.UNKNOWN) continue;
      this.out[pre].push([post, w * s]);
    }
    this.reset();
  }

  reset() {
    this.v = new Array(this.n).fill(this.p.v_rest);
    this.g = new Array(this.n).fill(0.0);
    this.refractoryUntil = new Array(this.n).fill(-1.0);
    this.pending = new Map();
    this.t = 0.0;
  }

  stimulate(ids, amount) {
    for (const i of ids) this.g[i] += amount;
  }

  // Returns spike counts as a Map from neuron index to count.
  run(durationMs) {
    const p = this.p;
    const steps = Math.round(durationMs / p.dt);
    const counts = new Map();
    const delaySteps = Math.max(1, Math.round(p.t_delay / p.dt));

    for (let k = 0; k < steps; k++) {
      const step = Math.round(this.t / p.dt);
      const landing = this.pending.get(step);
      if (landing) {
        this.pending.delete(step);
        for (const [post, w] of landing) this.g[post] += w;
      }

      const fired = [];
      for (let i = 0; i < this.n; i++) {
        if (this.t < this.refractoryUntil[i]) {
          this.v[i] = p.v_reset;
          this.g[i] += -this.g[i] * (p.dt / p.tau_s);
          continue;
        }
        const dv = (p.v_rest - this.v[i] + this.g[i]) / p.tau_m;
        this.v[i] += dv * p.dt;
        this.g[i] += (-this.g[i] / p.tau_s) * p.dt;
        if (this.v[i] > p.v_threshold) fired.push(i);
      }

      for (const i of fired) {
        this.v[i] = p.v_reset;
        this.g[i] = 0.0;
        this.refractoryUntil[i] = this.t + p.t_refractory;
        counts.set(i, (counts.get(i) || 0) + 1);
        const land = step + delaySteps;
        if (!this.pending.has(land)) this.pending.set(land, []);
        const bucket = this.pending.get(land);
        for (const e of this.out[i]) bucket.push(e);
      }

      this.t += p.dt;
    }
    return counts;
  }
}
