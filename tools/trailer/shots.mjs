// THE SHOT LIST: one place that says what the trailer shows, for how long and
// with which words. capture.mjs films it, music.py is written to its bars and
// montage.mjs cuts on them.
//
// Timing is in bars of the music (BPM below, 4/4). A shot is filmed for its
// bars plus one crossfade, so every cut lands on a bar line.
//
// Captions state facts only: counts from the packages, what the page does.
// Nothing here says an animal is smart, good at strategy, or feels anything.

export const BPM = 90;
export const BAR = (60 / BPM) * 4;          // 2.667 s
export const XFADE = 60 / BPM;              // one beat, 0.667 s
export const FPS = 30;
export const END_CARD = 6;                  // seconds, after the last shot

// The stage filmed: every species that can play, the worm twice (its own
// wiring and shuffled), and the mouse watching at the end of the row.
export const STAGE = [
  { species: "drosophila_female" }, { species: "drosophila_male" }, { species: "drosophila_larva" },
  { species: "c_elegans_herm" }, { species: "c_elegans_herm", shuffled: true }, { species: "c_elegans_male" },
  { species: "ciona_larva" }, { species: "zebrafish_larva" },
];

// Each shot is a function of the running stage (station x positions from the
// page) returning a camera spec for window.__rec.shot().
const brainOrbit = (x) => ({ kind: "orbit", center: [x - 1.05, 1.37, 0.1], from: [x - 0.72, 1.46, 0.72], sweep: -46, push: 0.12, rise: 0.03 });
export const SHOTS = [
  { name: "world", bars: 2, caption: ["Mapped animal brains,", "playing Open Doctrines."],
    cam: () => ({ kind: "dolly", from: [-0.45, 3.2, 1.7], to: [0.2, 3.35, 0.55], lookFrom: [-0.1, 3.35, -2.6], lookTo: [0.05, 3.36, -2.6] }) },
  { name: "room", bars: 2, caption: ["Each station: an animal,", "its screen, its brain."],
    cam: (s) => ({ kind: "dolly", from: [s.x[0] - 1.2, 2.3, 4.6], to: [s.x[0] + 2.4, 1.75, 2.9], lookFrom: [s.x[0] + 1.6, 1.0, -0.3], lookTo: [s.x[0] + 3.6, 1.0, -0.3] }) },
  { name: "fly-female", bars: 2, caption: ["138,639 neurons.", "A fruit fly."],
    cam: (s) => ({ kind: "orbit", center: [s.x[0], 0.82, 0.02], from: [s.x[0] + 0.28, 1.0, 0.5], sweep: 40, push: 0.14 }) },
  { name: "fly-female-brain", bars: 1.5, caption: ["Its orders come from spikes", "computed in your browser."],
    cam: (s) => brainOrbit(s.x[0]) },
  { name: "fly-male", bars: 1.5, caption: ["166,700 neurons.", "The male fly, mapped separately."],
    cam: (s) => ({ kind: "orbit", center: [s.x[1], 0.82, 0.02], from: [s.x[1] - 0.3, 0.98, 0.48], sweep: -36, push: 0.12 }) },
  { name: "worm", bars: 2, caption: ["302 neurons.", "A roundworm, on its plate."],
    cam: (s) => ({ kind: "orbit", center: [s.x[3], 0.765, 0.05], from: [s.x[3] + 0.2, 1.0, 0.38], sweep: 44, push: 0.1 }) },
  { name: "sea-squirt", bars: 1.5, caption: ["207 neurons.", "A sea squirt larva."],
    cam: (s) => ({ kind: "orbit", center: [s.x[6], 0.765, 0.05], from: [s.x[6] - 0.18, 1.0, 0.36], sweep: -40, push: 0.1 }) },
  { name: "larva", bars: 1.5, caption: ["2,952 neurons.", "A fly larva, in its food."],
    cam: (s) => ({ kind: "orbit", center: [s.x[2], 0.77, 0.05], from: [s.x[2] + 0.2, 1.0, 0.36], sweep: 40, push: 0.1 }) },
  { name: "zebrafish", bars: 2, caption: ["178,976 neurons.", "A zebrafish larva, seven days old."],
    cam: (s) => ({ kind: "orbit", center: [s.x[7], 1.03, 0.02], from: [s.x[7] + 0.35, 1.12, -0.62], sweep: -34, push: 0.12, fov: 38 }) },
  { name: "brains", bars: 2, caption: ["Each flash:", "one turn of spikes."],
    cam: (s) => ({ kind: "dolly", from: [s.x[0] - 2.75, 1.44, 0.62], to: [s.x[0] - 2.2, 1.4, 0.56], lookFrom: [s.x[2] - 1.05, 1.3, 0.02], lookTo: [s.x[2] - 1.05, 1.3, 0.02], fov: 40 }) },
  { name: "monitor", bars: 1.5, caption: ["Its screen: its country,", "its orders, its spikes."],
    cam: (s) => ({ kind: "dolly", from: [s.x[3] + 0.32, 1.2, 0.5], to: [s.x[3] + 0.18, 1.18, 0.28], lookFrom: [s.x[3] + 0.02, 1.16, -0.28], lookTo: [s.x[3] - 0.02, 1.16, -0.28] }) },
  { name: "shuffled", bars: 1.5, caption: ["The fair opponent: the same brain,", "with its wiring shuffled."],
    cam: (s) => { const m = (s.x[3] + s.x[4]) / 2; return { kind: "dolly", from: [m - 0.5, 1.75, 3.2], to: [m + 0.3, 1.55, 2.5], lookFrom: [m - 0.4, 0.95, 0], lookTo: [m - 0.3, 0.95, 0] }; } },
  { name: "mouse", bars: 1.5, caption: ["A mouse's visual cortex watches the map.", "It does not play."],
    cam: (s) => ({ kind: "orbit", center: [s.mouseX, 0.88, 0.1], from: [s.mouseX + 0.45, 1.05, 0.42], sweep: -30, push: 0.12 }) },
  { name: "mouse-eyes", bars: 1.5, caption: ["Through its eyes:", "a simulation of mouse vision."],
    cam: () => ({ kind: "mouseeyes" }) },
  { name: "finale", bars: 2, caption: null,
    cam: (s) => ({ kind: "dolly", from: [0, 1.9, 3.2], to: [0, 3.4, 11.5], lookFrom: [0, 1.6, -1.5], lookTo: [0, 1.9, -1.5], soft: 0.3 }) },
];

// Start time (s) of every shot in the cut, and the whole length.
export function timeline() {
  let t = 0;
  const shots = SHOTS.map((s) => { const o = { name: s.name, bars: s.bars, start: t, dur: s.bars * BAR, film: s.bars * BAR + XFADE, caption: s.caption }; t += s.bars * BAR; return o; });
  return { bpm: BPM, bar: BAR, xfade: XFADE, fps: FPS, shots, endCard: { start: t, dur: END_CARD }, total: t + END_CARD };
}
