// The stage, headless: Open Doctrines' own WebAssembly module under node, driven
// through the multi-seat calls the page uses. No brains -- this checks the
// game's side of a stage, which everything else stands on.
//
//   node tools/stage_check.mjs [path/to/web/agent]
//
// What it holds the engine to:
//   * every seat is its own country, with its own legal menus and budget
//   * orders sent to one seat are carried out for that seat
//   * the game's policy does NOT also play a seat. A seat that holds every turn
//     must not recruit; the same country left to the AI, same world, same seed,
//     does. Without the second half, a stage whose seats were quietly played by
//     the AI would pass every other check here and look like animals playing.
//   * two seats on one country are refused, not raced
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const agentDir = path.resolve(process.argv[2] || path.join(here, "..", "web", "agent"));
const { default: create } = await import(path.join(agentDir, "OpenDoctrinesAgent.mjs"));
const od = await create({ locateFile: (p) => path.join(agentDir, p), print: () => {}, printErr: () => {} });
const stageBegin = od.cwrap("od_agent_stage_begin", "number", ["string", "string", "number", "number"]);
const seatPos = (s, m = 0) => JSON.parse(od.cwrap("od_agent_seat_position", "string", ["number", "number"])(s, m));
const seatPlay = (s, t) => JSON.parse(od.cwrap("od_agent_seat_play", "string", ["number", "string"])(s, t));
const endTurn = od.cwrap("od_agent_end_turn", "number", []);

let failed = 0, checks = 0;
const check = (ok, what) => { checks++; if (!ok) failed++; console.log(`  ${ok ? "ok  " : "FAIL"}  ${what}`); };
const HOLD = "e:0,p:0,w:0,n:0";
const TURNS = 10, SEED = 4242;

// Every seat's recruit count over a run. `seats` plays; `watch` is read either way.
function run(isos, watch, playFor) {
  const n = stageBegin("1914:rung", isos.join(","), SEED, TURNS);
  if (n !== isos.length) return null;
  const armies = [];
  for (let t = 0; t < TURNS; t++) {
    for (let s = 0; s < n; s++) {
      const p = seatPos(s);
      if (p.iso === watch) armies.push(p.army);
      seatPlay(s, playFor(p, s));
    }
    if (!endTurn()) break;
  }
  return armies;
}

console.log("\n== three seats, one world ==");
const n = stageBegin("1914:rung", "FRA,GER,SWE", SEED, TURNS);
check(n === 3, `three seats taken (${n})`);
const ps = [0, 1, 2].map((s) => seatPos(s, s === 0 ? 1 : 0));
check(new Set(ps.map((p) => p.cid)).size === 3, `three different countries: ${ps.map((p) => `${p.iso}=${p.cid}`).join(" ")}`);
check(ps.every((p) => p.alive && p.mine > 0), "every seat holds land at the start");
check(ps.every((p) => Object.values(p.legal).some((l) => l.length > 1)), "every seat has something legal to do");
check(typeof ps[0].owners === "string" && ps[0].owners.length > 100, "the map comes with the position when asked for");
const g = ps[1];
const pick = Object.entries(g.legal).flatMap(([m, l]) => l.filter((x) => x.a > 0).slice(0, 1).map((x) => `${m}:${x.a}`));
const moves = seatPlay(1, pick.join(","));
check(moves.length === pick.length && moves.some((m) => m.outcome === "did"), `GER's orders are carried out for GER: ${moves.map((m) => `${m.token}=${m.outcome}`).join(" ")}`);
check(endTurn() === 1, "the world resolves a turn with every seat played");
check(seatPos(0).turn === ps[0].turn + 1, "and every seat sees the next turn");

console.log("\n== the game's policy does not also play a seat ==");
// A seat that holds every module every turn has decided to do nothing. If the
// policy were also playing it, it would recruit, fund and declare as it does
// for every AI country, and the seat's orders would be the policy's orders
// with the animal's added on top. Checked the other way on 2026-09-21: built
// with the skip in processCountryTurn removed, the holding seat's army went
// 4.7M -> 9.4M on turn one and this check failed, as it must.
const held = run(["FRA", "GER", "SWE"], "GER", () => HOLD);
check(held && held.length === TURNS, `GER read every turn as a holding seat (${held && held.length})`);
console.log(`       GER army, holding: ${held.join(" ")}`);
check(held.every((a, i) => i === 0 || a <= held[i - 1]), "a seat that holds never recruits");
const active = run(["FRA", "GER", "SWE"], "GER", (p, s) => (s === 1
  ? Object.entries(p.legal).flatMap(([m, l]) => l.filter((x) => x.name === "recruit").map((x) => `${m}:${x.a}`)).join(",")
  : HOLD));
console.log(`       GER army, recruiting: ${active.join(" ")}`);
check(active[active.length - 1] > held[held.length - 1], "and one told to recruit does, so the check can see recruiting");

console.log("\n== a seat researches, like every other country ==");
// Research is ~40% of an AI country's spending, and it was progressed for every
// country EXCEPT the player's, because a player sets it in the UI. Open Fly's
// fly IS the player, so it never researched at all, however it played. A seat
// still has to FUND research the way the policy does ("fund up"), so this seat
// funds and then holds; before the fix it could fund all it liked and nothing
// would ever progress.
{
  const LONG = 40;
  const fund = (p) => (Object.entries(p.legal).flatMap(([m, l]) => l.filter((x) => x.name === "fund up").map((x) => `${m}:${x.a}`))[0] || HOLD);
  const n = stageBegin("1914:rung", "FRA,GER", 4242, LONG);
  const nodes = [], shares = [];
  for (let t = 0; t < LONG && n === 2; t++) {
    const p = seatPos(0);
    nodes.push(p.researched); shares.push(+p.researchShare.toFixed(3));
    // Fund it, and pick something to research: a share with no focus finishes
    // nothing, which is how this first looked broken when it was not.
    const focus = Object.entries(p.legal).flatMap(([m, l]) => l.filter((x) => x.name === "focus bldg").map((x) => `${m}:${x.a}`))[0];
    seatPlay(0, t === 0 && focus ? focus : t < 12 ? fund(p) : HOLD);
    seatPlay(1, HOLD);
    if (!endTurn()) break;
  }
  console.log(`       FRA nodes researched: ${nodes[0]} -> ${nodes[nodes.length - 1]}`);
  console.log(`       FRA research share:   ${shares[0]} -> ${Math.max(...shares)}, working on "${seatPos(0).researching}"`);
  check(Math.max(...shares) > 0, "a seat that funds research has a research share");
  check(nodes[nodes.length - 1] > nodes[0], "and finishes nodes it would never have finished as the player");
}

console.log("\n== refusals ==");
check(stageBegin("1914:rung", "FRA,FRA", SEED, TURNS) === 0, "two seats on one country are refused");
check(stageBegin("1914:rung", "FRA,XXX", SEED, TURNS) === 0, "a country that does not exist is refused");

console.log(`\n${checks} checks, ${failed} failed`);
process.exit(failed ? 1 : 0);
