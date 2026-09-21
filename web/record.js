// RECORDING MODE, and the frame-exact capture the trailer is made from.
//
//   ?record    A "Record" control in the views bar, and the keys:
//                R      start / stop a MANUAL recording: fly and look with the
//                       usual controls (drag, W A S D, Q E, wheel) while it runs
//                T      start an AUTO TOUR: the camera orbits every animal and
//                       its brain in turn, then the world and the whole room,
//                       and the recording stops by itself at the end
//                Esc    stop whatever is running
//              While recording every panel is hidden, so the frame is clean.
//              The canvas is recorded with MediaRecorder (VP9 in WebM, high
//              bitrate) and downloaded when it stops.
//   ?capture   Time is virtual (index.html): nothing moves until the capture
//              script calls __oas.step(), which advances exactly 1/30 s. The
//              camera shots below are driven from window.__rec by
//              tools/trailer/capture.mjs.
//
// Everything here goes through window.__oas, which index.html sets only under
// ?record or ?capture; without either this file does nothing.

const Q = new URLSearchParams(location.search);
if (Q.has("record") || Q.has("capture")) boot();

async function boot() {
  while (!window.__oas) await new Promise((r) => setTimeout(r, 50));
  const O = window.__oas;
  const V3 = (a) => new THREE.Vector3(...a);

  // ------------------------------------------------------------ clean frame
  const css = document.createElement("style");
  css.textContent = `
    body.oas-clean .ident, body.oas-clean .views, body.oas-clean .setup, body.oas-clean .rail,
    body.oas-clean .statusbar, body.oas-clean .pov, body.oas-clean .loading { display: none !important; }
    body.oas-clean #stage { cursor: default; }
    .rec-btn i { background: #E0624F; }
    .rec-menu { position: fixed; top: 64px; right: 20px; z-index: 20; display: grid; gap: 6px; padding: 10px; border-radius: 12px; width: 250px; }
    .rec-menu[hidden] { display: none; }
    .rec-menu p { margin: 2px 2px 0; font-size: 11.5px; color: var(--muted); }
    .rec-menu button { text-align: left; }
    .rec-badge { position: fixed; left: 50%; bottom: 14px; transform: translateX(-50%); z-index: 20; font: 600 11px/1 var(--mono);
      letter-spacing: .12em; color: #FBD9D3; background: rgba(12,17,19,.7); border: 1px solid rgba(224,98,79,.5); border-radius: 999px;
      padding: 6px 11px; display: inline-flex; gap: 7px; align-items: center; transition: opacity 1s; pointer-events: none; }
    .rec-badge i { width: 7px; height: 7px; border-radius: 50%; background: #E0624F; animation: beat 1.4s ease-in-out infinite; }
    .rec-badge[data-dim="true"] { opacity: .35; }
    .rec-badge[hidden] { display: none; }`;
  document.head.appendChild(css);
  const clean = (on) => { document.body.classList.toggle("oas-clean", !!on); O.resize(); };

  // ------------------------------------------------------------ camera shots
  // A shot is a function of time t (seconds, may run a little before 0 or past
  // its duration, so two shots can overlap in a crossfade) returning where the
  // camera is and what it looks at. Motion inside a shot is at constant speed
  // with a gentle ease at the very ends; nothing ever jumps.
  const ease = (u) => (u <= 0 ? 0 : u >= 1 ? 1 : u * u * u * (u * (u * 6 - 15) + 10));   // smootherstep
  const lerp = (a, b, u) => a + (b - a) * u;
  const lerp3 = (a, b, u) => [lerp(a[0], b[0], u), lerp(a[1], b[1], u), lerp(a[2], b[2], u)];
  // Linear in the middle, eased over the first and last `soft` fraction, so a
  // lone shot starts and stops smoothly and a chained one keeps moving.
  const glide = (u, soft = 0.18) => {
    if (soft <= 0) return u;
    const s = soft, v = 1 / (1 - s);            // slope of the linear part
    if (u <= 0) return u * 0;                   // before the shot: hold the start
    if (u >= 1) return 1;
    if (u < s) return (v * u * u) / (2 * s);
    if (u > 1 - s) return 1 - (v * (1 - u) * (1 - u)) / (2 * s);
    return v * (u - s / 2);
  };

  // Orbit round `center` from where view `pos` stands, sweeping `sweep` degrees
  // (sign = direction), pushing in by `push` of the radius, rising by `rise`.
  function orbit({ center, from, sweep = 40, push = 0.12, rise = 0, dur = 5, soft = 0.18, lookLift = 0 }) {
    const dx = from[0] - center[0], dz = from[2] - center[2];
    const r0 = Math.hypot(dx, dz), a0 = Math.atan2(dx, dz), h = from[1] - center[1];
    const sw = (sweep * Math.PI) / 180;
    return { dur, at(t) {
      const u = glide(t / dur, soft), a = a0 - sw / 2 + sw * u, r = r0 * (1 - push * u);
      return { pos: [center[0] + Math.sin(a) * r, center[1] + h + rise * u, center[2] + Math.cos(a) * r], look: [center[0], center[1] + lookLift, center[2]] };
    } };
  }
  // A straight move between two poses, eased.
  function dolly({ from, to, lookFrom, lookTo, dur = 5, soft = 0.25 }) {
    return { dur, at(t) { const u = glide(t / dur, soft); return { pos: lerp3(from, to, u), look: lerp3(lookFrom, lookTo || lookFrom, u) }; } };
  }

  // The named shots, built from the page's own camera views so they follow
  // whatever stage is running (any number of seats, with or without the mouse).
  function shot(name, opt = {}) {
    const V = O.views(), v = V[name];
    if (!v) return null;
    const x = v.look[0];
    if (name === "wide") {
      const [px, py, pz] = v.pos;
      return dolly({ from: [px - 1.2, py + 0.6, pz + 0.6], to: [px + 1.2, py - 0.5, pz - 1.6], lookFrom: v.look, lookTo: [v.look[0], v.look[1] - 0.1, v.look[2]], dur: 6, ...opt });
    }
    if (name === "world") return dolly({ from: [-0.5, 2.85, 3.0], to: [0.35, 3.15, 1.35], lookFrom: [0, 3.3, -2.6], lookTo: [0, 3.35, -2.6], dur: 6, ...opt });
    if (name.startsWith("brain")) {
      // The brain floats 0.3 m above the pedestal's disc; orbit round it at
      // its own height, in front, where nothing stands between.
      const bx = v.look[0], c = [bx, 1.36, 0.1];
      return orbit({ center: c, from: [bx + 0.45, 1.5, 0.95], sweep: -50, push: 0.18, rise: 0.05, dur: 4.5, ...opt });
    }
    // An animal: round the point its view looks at, from its view.
    return orbit({ center: v.look, from: v.pos, sweep: 36, push: 0.14, rise: 0, dur: 5, ...opt });
  }

  // ------------------------------------------------------------ the driver
  // `run` is a list of { shot, dur }; consecutive shots overlap by `blend`
  // seconds, during which the camera is a smootherstep blend of both moving
  // cameras (lifted a little in an arc, so a long hop does not skim the desks).
  let run = null;
  function play(list, blend = 1.8, onDone) {
    const cur = { pos: O.camera.position.toArray(), look: O.camera.position.clone().add(new THREE.Vector3(0, 0, -1).applyEuler(O.camera.rotation)).toArray() };
    let t = 0; const segs = [];
    for (const s of list) { segs.push({ s, t0: t }); t += s.dur; }
    run = { segs, start: O.now(), total: t, blend, onDone, from: cur };
  }
  function poseAt(run, t) {
    const { segs, blend } = run;
    let i = segs.findIndex((g) => t < g.t0 + g.s.dur); if (i < 0) i = segs.length - 1;
    const a = segs[i];
    let p = a.s.at(t - a.t0);
    // Crossing into the next shot: the last blend/2 of this one and the first
    // blend/2 of the next are both running.
    const nxt = segs[i + 1], prv = segs[i - 1];
    const mix = (A, B, w, hop) => {
      const e = ease(w), d = Math.hypot(B.pos[0] - A.pos[0], B.pos[2] - A.pos[2]);
      const pos = lerp3(A.pos, B.pos, e); pos[1] += Math.sin(Math.PI * e) * Math.min(0.6, d * 0.12) * hop; pos[2] += Math.sin(Math.PI * e) * Math.min(0.8, d * 0.15) * hop;
      return { pos, look: lerp3(A.look, B.look, e) };
    };
    const end = a.t0 + a.s.dur;
    if (nxt && t > end - blend / 2) { const w = (t - (end - blend / 2)) / blend; p = mix(p, nxt.s.at(t - nxt.t0), w, 1); }
    else if (prv && t < a.t0 + blend / 2) { const w = (t - (a.t0 - blend / 2)) / blend; p = mix(prv.s.at(t - prv.t0), p, w, 1); }
    // Ease in from wherever the camera was when the tour started.
    if (t < blend) p = mix(run.from, p, t / blend, 0);
    return p;
  }
  O.beforeRender = () => {
    if (!run || O.inPov()) return;
    const t = O.now() - run.start;
    const p = poseAt(run, Math.min(t, run.total));
    O.aim(p.pos, p.look);
    if (t >= run.total) { const done = run.onDone; run = null; done && done(); }
  };

  // The whole room, one animal at a time: the tour the recorder plays.
  function tourList() {
    const V = O.views(), out = [shot("wide", { dur: 6, soft: 0 })];
    for (let i = 0; V[`seat${i}`]; i++) out.push(shot(`seat${i}`, { soft: 0 }), shot(`brain${i}`, { soft: 0 }));
    if (V.mouse) out.push(shot("mouse", { soft: 0 }), shot("brainmouse", { soft: 0 }));
    out.push(shot("world", { dur: 7, soft: 0 }), shot("wide", { dur: 6, soft: 0.3 }));
    return out.filter(Boolean);
  }

  if (O.capture) return captureApi(O, { shot, orbit, dolly, play, poseAt, clean });
  recorderUi(O, { clean, play, tourList, stopTour: () => { run = null; } });
}

// ============================================================ ?record
function recorderUi(O, { clean, play, tourList, stopTour }) {
  const views = document.getElementById("views");
  const menu = document.createElement("div"); menu.className = "rec-menu glass"; menu.hidden = true;
  menu.innerHTML = `<button type="button" data-m="tour">Auto tour <small>(T)</small></button>
    <button type="button" data-m="manual">Record while I fly <small>(R)</small></button>
    <p>Hides every panel and records the 3D view to a .webm file. Esc stops.</p>`;
  document.body.appendChild(menu);
  const btn = document.createElement("button"); btn.type = "button"; btn.className = "rec-btn"; btn.innerHTML = "<i></i>Record";
  btn.addEventListener("click", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; });
  // The views bar is rebuilt for every stage; put the button back each time.
  const place = () => { if (!views.contains(btn)) views.appendChild(btn); };
  new MutationObserver(place).observe(views, { childList: true }); place();
  menu.addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; menu.hidden = true; start(b.dataset.m); });
  addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target) && e.target !== btn) menu.hidden = true; });

  const badge = document.createElement("div"); badge.className = "rec-badge"; badge.hidden = true; document.body.appendChild(badge);
  let rec = null;

  // A 4K canvas is more than a real-time VP9 encoder keeps up with, and a
  // dropped frame is a stutter in the file. While recording, the canvas is at
  // most 1920 px wide (a 1080p file); the brains' point sizes follow.
  function capRatio(on) {
    const r = O.renderer, prev = on ? r.getPixelRatio() : rec.ratio;
    const next = on ? Math.min(prev, Math.max(1, 1920 / innerWidth)) : rec.ratio;
    if (on && O.inPov()) return prev;
    r.setPixelRatio(next); O.resize();
    const all = [...O.G.seats.map((s) => s.st), O.G.mouse && O.G.mouse.st].filter(Boolean);
    for (const st of all) if (st.brain) st.brain.mat.uniforms.uPixel.value = next;
    return prev;
  }

  function start(mode) {
    if (rec) return stop();
    if (!window.MediaRecorder || !O.canvas.captureStream) { alert("This browser cannot record a canvas (MediaRecorder)."); return; }
    O.exitMouseEyes();
    const type = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((t) => MediaRecorder.isTypeSupported(t));
    // Everything below reads `r`, not `rec`: the last chunk and onstop arrive
    // after stop() has already cleared `rec`.
    const r = rec = { mode, chunks: [], t0: performance.now() };
    r.ratio = capRatio(true);
    clean(true);
    const stream = O.canvas.captureStream(60);
    const mr = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: 16_000_000 });
    r.mr = mr; r.type = type;
    mr.ondataavailable = (e) => { if (e.data && e.data.size) r.chunks.push(e.data); };
    mr.onstop = () => save(r);
    mr.start(1000);
    badge.hidden = false; badge.dataset.dim = "false";
    r.timer = setInterval(() => {
      const s = Math.floor((performance.now() - r.t0) / 1000);
      badge.innerHTML = `<i></i>REC ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} · ${mode === "tour" ? "auto tour" : "fly around"} · Esc to stop`;
      if (s >= 3) badge.dataset.dim = "true";
    }, 250);
    if (mode === "tour") play(tourList(), 1.8, () => setTimeout(stop, 400));
    O.canvas.focus();
  }
  function stop() {
    if (!rec) return;
    const r = rec;
    stopTour(); clearInterval(r.timer); badge.hidden = true;
    if (r.mr.state !== "inactive") r.mr.stop();
    capRatio(false); clean(false);
    rec = null;
  }
  function save(r) {
    const blob = new Blob(r.chunks, { type: "video/webm" });
    const a = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    a.href = URL.createObjectURL(blob); a.download = `open-animal-stage-${r.mode}-${stamp}.webm`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 60_000);
    window.__recLast = { bytes: blob.size, name: a.download, type: r.type };
  }
  addEventListener("keydown", (e) => {
    if (e.target.closest && e.target.closest("select, input, textarea")) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.code === "Escape" && rec) { e.preventDefault(); stop(); }
    else if (e.code === "KeyR") { e.preventDefault(); rec ? stop() : start("manual"); }
    else if (e.code === "KeyT" && !rec) { e.preventDefault(); start("tour"); }
  });
  window.__recUi = { start, stop, get recording() { return !!rec; } };
}

// ============================================================ ?capture
// Driven by tools/trailer/capture.mjs over the DevTools protocol.
function captureApi(O, { shot, orbit, dolly, play, poseAt, clean }) {
  // TURNS ON THE VIRTUAL CLOCK. The game loop paces itself in real time, and a
  // capture runs several times slower than real time, so on screen the turns
  // would race. Each endTurn is held until `turnEvery` virtual seconds have
  // passed since the last, which makes the brains flash at a steady beat.
  const rec = { turnEvery: 2.4, lastTurn: 0, single: null };
  const call = O.game.call;
  O.game.call = async (type, ...rest) => {
    if (type === "endTurn") { while (O.now() - rec.lastTurn < rec.turnEvery) await new Promise((r) => setTimeout(r, 15)); rec.lastTurn = O.now(); }
    return call(type, ...rest);
  };
  let current = null;
  O.beforeRender = () => {
    if (!current || O.inPov()) return;
    const p = current.s.at(O.now() - current.t0);
    O.aim(p.pos, p.look);
  };
  window.__rec = {
    clean,
    set turnEvery(s) { rec.turnEvery = s; },
    // Everything a shot needs is on screen: the game is past its first turns,
    // every seat has a brain on its pedestal (or has faulted), the mouse too.
    status() {
      const G = O.G;
      return { turn: G.turn, seats: G.seats.map((s) => ({ id: s.species.id, shuffled: s.shuffled, state: s.state, brain: !!(s.st && s.st.brain), turns: s.turns.length, x: s.st ? s.st.g.position.x : null, deskTop: s.st ? s.st.deskTop : null })),
        mouseX: G.mouse && G.mouse.st ? G.mouse.st.g.position.x : null,
        mouse: G.mouse ? { state: G.mouse.state, brain: !!(G.mouse.st && G.mouse.st.brain), looks: G.mouse.looks } : null, views: Object.keys(O.views()) };
    },
    // Set up a shot. spec: { view, dur, ...orbit/dolly options } or
    // { kind: "orbit"|"dolly", ... } or { kind: "mouseeyes" }.
    shot(spec) {
      O.exitMouseEyes();
      let s;
      if (spec.kind === "mouseeyes") { O.enterMouseEyes(); current = null; return { dur: spec.dur || 4 }; }
      if (spec.kind === "orbit") s = orbit(spec);
      else if (spec.kind === "dolly") s = dolly(spec);
      else s = shot(spec.view, spec);
      if (!s) throw new Error(`no view ${spec.view}`);
      // A longer lens for a small subject; back to the page's 50 degrees after.
      O.camera.fov = spec.fov || 50; O.camera.updateProjectionMatrix();
      current = { s, t0: O.now() + (spec.lead || 0) };
      O.beforeRender();
      return { dur: s.dur };
    },
    end() { current = null; O.exitMouseEyes(); O.camera.fov = 50; O.camera.updateProjectionMatrix(); },
  };
}
