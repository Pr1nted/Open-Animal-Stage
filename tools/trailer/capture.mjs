// Films the shot list (shots.mjs) frame by frame in headless Chrome.
//
//   node tools/trailer/capture.mjs [--base http://127.0.0.1:8110/] [--gl gpu|swiftshader]
//                                  [--stills] [--only world,fly-female] [--out out/trailer]
//
// The page runs under ?capture, where its clock is virtual: each frame is one
// __oas.step() (exactly 1/30 s of animation) followed by a screenshot, so the
// motion is perfectly even however long a frame takes to grab. --stills grabs
// one frame from the middle of each shot instead, for checking framing.
// Without --base it serves web/ itself on a free port.
import { launch } from "./cdp.mjs";
import { SHOTS, STAGE, FPS, timeline } from "./shots.mjs";
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i < 0 ? d : process.argv[i + 1]; };
const has = (k) => process.argv.includes(`--${k}`);
const OUT = resolve(ROOT, arg("out", "out/trailer"));
const STILLS = has("stills");
const ONLY = arg("only", null) ? new Set(arg("only").split(",")) : null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function freePort() {
  return new Promise((res) => { const s = createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); });
}
let server = null, base = arg("base", null);
if (!base) {
  const port = await freePort();
  server = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1", "--directory", join(ROOT, "web")], { stdio: "ignore" });
  base = `http://127.0.0.1:${port}/`;
  for (let i = 0; i < 50; i++) { try { await fetch(base); break; } catch (_) { await sleep(100); } }
}
const cleanup = async (p) => { if (p) await p.close(); if (server) server.kill(); };

const p = await launch({ gl: arg("gl", "gpu") });
p.on("Runtime.exceptionThrown", (e) => log("page exception:", (e.exceptionDetails.exception?.description || e.exceptionDetails.text).slice(0, 300)));
try {
  await p.goto(`${base}?capture`);
  const gl = await p.eval(`(() => { const g = document.createElement("canvas").getContext("webgl"); const d = g && g.getExtension("WEBGL_debug_renderer_info"); return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : String(!!g); })()`);
  log("WebGL:", gl);
  // The page renders only when stepped, so it is stepped while it loads.
  const tick = async (n = 1) => p.eval(`window.__oas && window.__oas.step(${n})`);
  for (let i = 0; ; i++) {
    const ok = await p.eval(`document.getElementById("loading").dataset.done === "true" && !!window.__rec && document.querySelectorAll("#presets button").length > 0`);
    if (ok) break;
    if (i > 600) throw new Error("the page did not finish loading");
    await sleep(200);
  }
  // Seat the stage the way a viewer would: the "Everyone" preset, one more
  // seat, then each row set to its animal and wiring.
  await p.eval(`(async () => {
    const want = ${JSON.stringify(STAGE)};
    const pre = [...document.querySelectorAll("#presets button")].find((b) => /Everyone|first/.test(b.textContent)) || document.querySelector("#presets button");
    pre.click();
    while (document.querySelectorAll("#seatRows .seatrow").length < want.length) document.getElementById("addSeat").click();
    const set = (i, k, v) => { const el = document.querySelector('#seatRows select[data-i="' + i + '"][data-k="' + k + '"]'); el.value = v; el.dispatchEvent(new Event("change")); };
    want.forEach((w, i) => { set(i, "species", w.species); set(i, "shuffled", w.shuffled ? "1" : ""); });
    document.getElementById("mouseOn").checked = true;
    document.getElementById("startBtn").click();
  })()`);
  log("stage requested; waiting for every brain and a few turns");
  let st = null;
  const t0 = Date.now();
  for (;;) {
    await tick(2);
    st = await p.eval(`window.__rec.status()`);
    const ready = st.seats.length === STAGE.length && st.seats.every((s) => s.brain || s.state === "fault") && (!st.mouse || st.mouse.brain) && st.turn >= 3;
    if (ready) break;
    if ((Date.now() - t0) % 10000 < 120) log(`turn ${st.turn}`, st.seats.map((s) => `${s.id.split("_").pop()}:${s.brain ? "B" : s.state}`).join(" "), st.mouse ? `mouse:${st.mouse.brain ? "B" : st.mouse.state}` : "");
    if (Date.now() - t0 > 15 * 60e3) throw new Error("the stage did not get ready in 15 minutes");
    await sleep(100);
  }
  log("ready:", st.seats.map((s) => `${s.id}${s.shuffled ? "*" : ""}:${s.state}`).join(" "));
  const faulted = st.seats.filter((s) => s.state === "fault");
  if (faulted.length) log("WARNING faulted seats:", faulted.map((s) => s.id).join(", "));
  await p.eval(`window.__rec.clean(true)`);
  const where = { x: st.seats.map((s) => s.x), mouseX: st.mouseX };

  const tl = timeline();
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, "timeline.json"), JSON.stringify(tl, null, 2));
  const dir = join(OUT, STILLS ? "stills" : "frames");
  mkdirSync(dir, { recursive: true });
  for (const [k, shot] of SHOTS.entries()) {
    if (ONLY && !ONLY.has(shot.name)) continue;
    const film = tl.shots[k].film, n = Math.round(film * FPS);
    const spec = shot.cam(where);
    await p.eval(`window.__rec.shot(${JSON.stringify(spec)})`);
    const tag = `${String(k).padStart(2, "0")}-${shot.name}`;
    if (STILLS) {
      await tick(Math.round(n / 2));
      writeFileSync(join(dir, `${tag}.png`), await p.png());
      log("still", tag);
      continue;
    }
    const sd = join(dir, tag); rmSync(sd, { recursive: true, force: true }); mkdirSync(sd, { recursive: true });
    const s0 = Date.now();
    for (let f = 0; f < n; f++) {
      await tick(1);
      writeFileSync(join(sd, `${String(f).padStart(5, "0")}.png`), await p.png());
    }
    log(`${tag}: ${n} frames in ${((Date.now() - s0) / 1000).toFixed(1)} s`);
  }
  await p.eval(`window.__rec.end()`);
  log("done");
} catch (e) {
  log("capture failed:", e.message);
  process.exitCode = 1;
} finally {
  await cleanup(p);
}
