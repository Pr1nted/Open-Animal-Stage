// Any animal's brain, in the browser: one engine for every species on the stage.
//
// The neuron is Open Fly's, which is Shiu et al. (Nature 2024) ported off Brian2
// and checked spike for spike against it:
//
//   dv/dt = (v_0 - v + g) / t_mbr     (frozen while refractory)
//   dg/dt = -g / tau                   (frozen while refractory)
//   spike when v > v_th; then v = v_rst, g = 0, refractory for t_rfc
//   a spike adds w = count * w_syn to g of each target, t_dly later
//   a sensory input spike adds w_syn * f_poi to v of its neuron at once
//
// step() below is Open Fly's FlyBrain.step with two additions, and neither runs
// for a species that does not need it: with no gap junctions and no shuffle this
// is the same arithmetic in the same order, so the female fly on this stage is
// the fly Open Fly validated. tools/check_fly_identity.mjs holds it to that.
//
// ELECTRICAL SYNAPSES. The worm and the sea squirt are wired by gap junctions as
// much as by chemical synapses -- a fifth of the sea squirt's wiring -- and a
// gap junction is not a delayed kick to g, it is a current that flows both ways
// for as long as two neurons differ. After integration each step, a junction of
// strength s between i and j moves v_i by w_gap * s * (v_j - v_i) * dt / t_mbr,
// and v_j the other way; refractory neurons are frozen and take no part. A
// neuron with a junction never goes to sleep, because a coupled neighbour can
// move it without a spike: the event-driven shortcut is only safe for neurons
// whose every input arrives as an event.
//
// THE SHUFFLED CONTROL. shuffle(seed) permutes the postsynaptic column of the
// connectome (and the far end of every gap junction). Every neuron keeps its
// out-degree, in-degree, sign, and the exact weights it sends; sensory and motor
// sets do not move. Parallel edges that the permutation creates stay two entries
// and are both delivered, so nothing merges and no weight is lost -- the failure
// open_animal_stage/shuffle.py records for a merging shuffle. Self-loops are
// swapped away. What changes is who is wired to whom, and nothing else, which
// is what makes it the one opponent on the stage that isolates the wiring.

export class AnimalBrain {
  constructor(connectome, meta) {
    const dv = new DataView(connectome);
    const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
    let off, n, nsyn, ngap = 0;
    if (magic === "OAS1") {
      n = dv.getUint32(4, true); nsyn = dv.getUint32(8, true); ngap = dv.getUint32(12, true); off = 16;
    } else if (magic === "SFC1") {                  // Open Fly's own file, as it ships
      n = dv.getUint32(4, true); nsyn = dv.getUint32(8, true); off = 12;
    } else throw new Error(`connectome.bin: unknown header "${magic}"`);
    this.n = n; this.nsyn = nsyn; this.ngap = ngap;
    this.indptr = new Uint32Array(connectome, off, n + 1); off += (n + 1) * 4;
    this.post = new Uint32Array(connectome, off, nsyn); off += nsyn * 4;
    this.count = new Int16Array(connectome, off, nsyn); off += nsyn * 2;
    // Open Fly's SFC1 ends here with no padding, so the gap arrays are only
    // located when there are any.
    if (ngap) {
      off = (off + 3) & ~3;
      this.gapA = new Uint32Array(connectome, off, ngap); off += ngap * 4;
      this.gapB = new Uint32Array(connectome, off, ngap); off += ngap * 4;
      this.gapW = new Float32Array(connectome, off, ngap); off += ngap * 4;
    } else { this.gapA = new Uint32Array(0); this.gapB = new Uint32Array(0); this.gapW = new Float32Array(0); }
    if (off > connectome.byteLength) throw new Error("connectome.bin is shorter than its header says");
    for (let i = 0; i < n; i++) if (this.indptr[i] > this.indptr[i + 1]) throw new Error("connectome.bin: indptr is not monotone");
    if (this.indptr[n] !== nsyn) throw new Error("connectome.bin: indptr does not end at the synapse count");

    const P = meta.params;
    this.P = P;
    this.dt = P.dt;
    this.em = Math.exp(-P.dt / P.t_mbr);
    this.es = Math.exp(-P.dt / P.tau);
    this.k = P.tau / (P.tau - P.t_mbr);
    this.delaySteps = Math.round(P.t_dly / P.dt);
    this.rfcSteps = Math.round(P.t_rfc / P.dt);
    this.wSyn = P.w_syn;
    this.wPoisson = P.w_syn * P.f_poi;
    this.gapGain = ngap && P.w_gap ? P.w_gap * P.dt / P.t_mbr : 0;
    this.v = new Float64Array(n).fill(P.v_0);
    this.g = new Float64Array(n);
    this.rfc = new Uint16Array(n);
    this.noRfc = new Uint8Array(n);
    this.awake = new Uint8Array(n);
    this.awakeList = new Int32Array(n);
    this.awakeCount = 0;
    // Neurons a junction can move without a spike, kept awake for good.
    this.pinned = new Uint8Array(n);
    if (this.gapGain) for (let e = 0; e < ngap; e++) { this.pinned[this.gapA[e]] = 1; this.pinned[this.gapB[e]] = 1; }
    this.sensory = {};
    for (const [ch, idx] of Object.entries(meta.sensory)) {
      this.sensory[ch] = Int32Array.from(idx);
      for (const i of idx) this.noRfc[i] = 1;
    }
    this.ring = [];
    for (let s = 0; s <= this.delaySteps; s++) this.ring.push({ post: new Int32Array(1 << 12), w: new Float64Array(1 << 12), len: 0 });
    this.head = 0;
    this.spikesStep = new Int32Array(n);
    this.shuffled = null;
    this.wakePinned();
  }

  wakePinned() { for (let i = 0; i < this.n; i++) if (this.pinned[i]) this.wake(i); }

  // The control. Deterministic in `seed`, so a shuffled seat is the same brain
  // every game and can be reported as one. Takes a copy: the real wiring stays
  // in the buffer, untouched, for anything else that reads it.
  shuffle(seed) {
    const rand = mulberry32(seed >>> 0);
    const post = Uint32Array.from(this.post);
    const owner = new Uint32Array(this.nsyn);
    for (let i = 0; i < this.n; i++) for (let e = this.indptr[i]; e < this.indptr[i + 1]; e++) owner[e] = i;
    for (let e = post.length - 1; e > 0; e--) {
      const j = Math.floor(rand() * (e + 1)); const t = post[e]; post[e] = post[j]; post[j] = t;
    }
    // Self-loops: swap the target with another edge's where neither becomes one.
    let loops = 0;
    for (let e = 0; e < post.length; e++) {
      if (post[e] !== owner[e]) continue;
      for (let tries = 0; tries < 64; tries++) {
        const j = Math.floor(rand() * post.length);
        if (post[j] !== owner[e] && post[e] !== owner[j]) { const t = post[e]; post[e] = post[j]; post[j] = t; break; }
        if (tries === 63) loops++;
      }
    }
    this.post = post;
    if (this.ngap) {
      const b = Uint32Array.from(this.gapB);
      for (let e = b.length - 1; e > 0; e--) { const j = Math.floor(rand() * (e + 1)); const t = b[e]; b[e] = b[j]; b[j] = t; }
      for (let e = 0; e < b.length; e++) if (b[e] === this.gapA[e]) { const j = (e + 1) % b.length; const t = b[e]; b[e] = b[j]; b[j] = t; }
      this.gapB = b;
    }
    this.shuffled = { seed: seed >>> 0, unresolvedSelfLoops: loops };
    return this.shuffled;
  }

  wake(i) {
    if (!this.awake[i]) { this.awake[i] = 1; this.awakeList[this.awakeCount++] = i; }
  }

  push(bucket, target, w) {
    if (bucket.len === bucket.post.length) {
      const p = new Int32Array(bucket.post.length * 2); p.set(bucket.post); bucket.post = p;
      const ww = new Float64Array(bucket.w.length * 2); ww.set(bucket.w); bucket.w = ww;
    }
    bucket.post[bucket.len] = target; bucket.w[bucket.len] = w; bucket.len++;
  }

  // One 0.1 ms step. `rates` is Hz per channel; `counts` collects spikes (or null).
  step(rates, rand, counts) {
    const { v, g, rfc, noRfc, P, em, es, k, pinned } = this;
    const v0 = P.v_0, vth = P.v_th;
    let live = 0, nSpk = 0;
    const list = this.awakeList, spk = this.spikesStep;
    for (let j = 0; j < this.awakeCount; j++) {
      const i = list[j];
      if (rfc[i] > 0) { list[live++] = i; continue; }
      const gi = g[i];
      const vi = v0 + (v[i] - v0 - k * gi) * em + k * gi * es;
      const gn = gi * es;
      v[i] = vi; g[i] = gn;
      if (vi > vth) spk[nSpk++] = i;
      if (!pinned[i] && Math.abs(vi - v0) < 1e-5 && Math.abs(gn) < 1e-6) { v[i] = v0; g[i] = 0; this.awake[i] = 0; }
      else list[live++] = i;
    }
    this.awakeCount = live;
    if (this.gapGain) {
      // Both ends read before either moves, so a junction's order in the list
      // does not decide which way current flows first.
      const A = this.gapA, B = this.gapB, W = this.gapW, c = this.gapGain;
      for (let e = 0; e < A.length; e++) {
        const a = A[e], b = B[e];
        if (rfc[a] > 0 || rfc[b] > 0) continue;
        const d = c * W[e] * (v[b] - v[a]);
        v[a] += d; v[b] -= d;
      }
      // A junction can carry a neuron over threshold; it spikes this step, as
      // one pushed there by integration does.
      for (let e = 0; e < A.length; e++) for (const i of [A[e], B[e]]) {
        if (rfc[i] === 0 && v[i] > vth && !this.spikeMarked(i, nSpk)) spk[nSpk++] = i;
      }
    }
    const bucket = this.ring[this.head];
    for (let s = 0; s < bucket.len; s++) {
      const t = bucket.post[s];
      if (rfc[t] > 0) continue;
      g[t] += bucket.w[s];
      this.wake(t);
    }
    bucket.len = 0;
    for (const ch in this.sensory) {
      const r = rates[ch] || 0;
      if (r <= 0) continue;
      const p = r * this.dt * 1e-3;
      const idx = this.sensory[ch];
      for (let s = 0; s < idx.length; s++) {
        if (rand() < p) { const t = idx[s]; if (rfc[t] > 0) continue; v[t] += this.wPoisson; this.wake(t); }
      }
    }
    const target = this.ring[(this.head + this.delaySteps) % this.ring.length];
    for (let s = 0; s < nSpk; s++) {
      const i = spk[s];
      v[i] = P.v_rst; g[i] = 0;
      rfc[i] = noRfc[i] ? 0 : this.rfcSteps;
      if (counts) counts[i]++;
      for (let e = this.indptr[i], end = this.indptr[i + 1]; e < end; e++) {
        this.push(target, this.post[e], this.count[e] * this.wSyn);
      }
    }
    for (let j = 0; j < this.awakeCount; j++) { const i = list[j]; if (rfc[i] > 0) rfc[i]--; }
    this.head = (this.head + 1) % this.ring.length;
  }

  // Linear, but only ever over this step's few spikes and only for coupled species.
  spikeMarked(i, nSpk) { const spk = this.spikesStep; for (let s = 0; s < nSpk; s++) if (spk[s] === i) return true; return false; }

  runWindow(rates, windowMs, seed, flushMs = 2.0) {
    const rand = mulberry32(seed >>> 0);
    const flushSteps = Math.round(flushMs / this.dt);
    for (let s = 0; s < flushSteps; s++) this.step({}, rand, null);
    for (let j = 0; j < this.awakeCount; j++) {
      const i = this.awakeList[j];
      this.v[i] = this.P.v_0; this.g[i] = 0;
    }
    const counts = new Uint16Array(this.n);
    const steps = Math.round(windowMs / this.dt);
    for (let s = 0; s < steps; s++) this.step(rates, rand, counts);
    return counts;
  }
}

export function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
