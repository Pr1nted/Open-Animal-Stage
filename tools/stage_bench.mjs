// Which mapping does better, measured the way PREREGISTRATION.md ("The
// benchmark") says, headless, with the page's own brains and the page's own game.
//
//   node tools/stage_bench.mjs --plan bench/plan.json --jobs 6 --out data/bench/run.json
//   node tools/stage_bench.mjs --one '{"player":"c_elegans_herm","seat":"1914:FRA","seed":101,"turns":120}'
//
// Every player takes the SAME seat on the SAME world seed, alone against the
// game's AI, so two players differ only in who played that country. Players:
//   <species id>            the animal's brain and mapping, as on the stage
//   <species id>:shuffled   the same brain rewired (brain.js shuffle, seed 783)
//   hold                    sends nothing but "hold": the floor
//   random                  a random legal pick per module, up to the budget,
//                           from a per-turn seeded draw: chance
//
// A game's score is the change in land share, percentage points, end minus
// start; wiped out counts as ending on zero. The report pairs every player with
// hold and with its own shuffled control on the same seat and seed, because a
// difference between seats is mostly a difference between countries.
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";
import { AnimalBrain, mulberry32 } from "../web/brain.js";
import { Encoder, choose, turnSeed, BRAIN_SEED, WINDOW_MS } from "../web/decide.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.join(here, "..", "web");
const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d; };

// ---------------------------------------------------------------- one game
function connectome(id) {
  const dir = path.join(web, "species", id);
  const bin = path.join(dir, "connectome.bin");
  if (existsSync(bin)) { const b = readFileSync(bin); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); }
  const m = JSON.parse(readFileSync(path.join(dir, "connectome.pack.json"), "utf8"));
  let b = Buffer.concat(m.parts.map((p) => readFileSync(path.join(dir, p))));
  if (b[0] === 0x1f && b[1] === 0x8b) b = zlib.gunzipSync(b);
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
}

async function playOne({ player, seat, seed, turns }) {
  const t0 = Date.now();
  const agentDir = path.join(web, "agent");
  const { default: create } = await import(path.join(agentDir, "OpenDoctrinesAgent.mjs"));
  const od = await create({ locateFile: (p) => path.join(agentDir, p), print: () => {}, printErr: () => {} });
  const stage = od.cwrap("od_agent_stage_begin", "number", ["string", "string", "number", "number"]);
  const pos = () => JSON.parse(od.cwrap("od_agent_seat_position", "string", ["number", "number"])(0, 0));
  const play = (t) => JSON.parse(od.cwrap("od_agent_seat_play", "string", ["number", "string"])(0, t));
  const endTurn = od.cwrap("od_agent_end_turn", "number", []);
  const [map, iso] = seat.split(":");
  if (stage(`${map}:rung`, iso, seed >>> 0, turns) !== 1) throw new Error(`could not seat ${seat}`);

  let brain = null, meta = null, motor = null;
  const [species, variant] = player.split(":");
  if (player !== "hold" && player !== "random") {
    meta = JSON.parse(readFileSync(path.join(web, "species", species, "brain.json"), "utf8"));
    brain = new AnimalBrain(connectome(species), meta);
    if (variant === "shuffled") brain.shuffle(783);
    motor = Int32Array.from(meta.motor || meta.dn || []);
  }
  const enc = new Encoder();
  let start = null, last = null, landless = 0, wiped = null, orders = 0, motorSpikes = 0, played = 0;
  for (;;) {
    const p = pos(); last = p;
    if (start === null) start = p.share;
    if (p.over) break;
    landless = p.mine === 0 ? landless + 1 : 0;
    if (landless >= 2) { wiped = p.turn; break; }
    const tSeed = turnSeed(BRAIN_SEED, p.iso, p.turn);
    let tokens;
    if (player === "hold") tokens = ["e:0", "p:0", "w:0", "n:0"];
    else if (player === "random") {
      const rand = mulberry32(tSeed);
      tokens = [];
      for (const [m, list] of Object.entries(p.legal)) {
        const acts = list.map((x) => x.a).filter((a) => a !== 0);
        for (let k = 0; k < (p.budget[m] | 0) && acts.length; k++) tokens.push(`${m}:${acts.splice(Math.floor(rand() * acts.length), 1)[0]}`);
      }
    } else {
      const { rates } = enc.rates(p, meta.senses || {});
      const counts = brain.runWindow(rates, meta.window_ms || WINDOW_MS, tSeed);
      for (const i of motor) motorSpikes += counts[i];
      tokens = choose(counts, meta.groups, p, tSeed).tokens;
    }
    orders += play(tokens.join(",")).filter((m) => m.outcome === "did" && !m.token.endsWith(":0")).length;
    played++;
    if (endTurn() !== 1) { last = pos(); break; }
  }
  return {
    player, seat, seed, turns, country: last.name,
    start_share: start, end_share: wiped === null ? last.share : 0, wiped_turn: wiped,
    score: (wiped === null ? last.share : 0) - start,
    turns_played: played, orders_per_turn: +(orders / Math.max(1, played)).toFixed(2),
    motor_spikes_per_turn: brain ? Math.round(motorSpikes / Math.max(1, played)) : null,
    research_end: last.researched ?? null, seconds: Math.round((Date.now() - t0) / 1000),
  };
}

// ---------------------------------------------------------------- statistics
function meanCI(xs, reps = 4000, seed = 7) {
  const n = xs.length, mean = xs.reduce((a, b) => a + b, 0) / (n || 1);
  if (n < 2) return { n, mean, lo: NaN, hi: NaN };
  const rand = mulberry32(seed), boots = [];
  for (let r = 0; r < reps; r++) { let s = 0; for (let i = 0; i < n; i++) s += xs[Math.floor(rand() * n)]; boots.push(s / n); }
  boots.sort((a, b) => a - b);
  return { n, mean, lo: boots[Math.floor(reps * 0.025)], hi: boots[Math.floor(reps * 0.975)] };
}
const fmt = (x) => (x >= 0 ? "+" : "") + x.toFixed(2);
const ci = (c) => `${fmt(c.mean)} [${fmt(c.lo)}, ${fmt(c.hi)}]`;

function report(games, plan) {
  const key = (g) => `${g.seat}|${g.seed}`;
  const byPlayer = new Map();
  for (const g of games) { if (!byPlayer.has(g.player)) byPlayer.set(g.player, new Map()); byPlayer.get(g.player).set(key(g), g); }
  const paired = (a, b) => {           // a minus b, on the seats and seeds both played
    const A = byPlayer.get(a), B = byPlayer.get(b); if (!A || !B) return null;
    const d = [...A.keys()].filter((k) => B.has(k)).map((k) => A.get(k).score - B.get(k).score);
    return d.length ? meanCI(d) : null;
  };
  const rows = [...byPlayer.keys()].map((p) => {
    const gs = [...byPlayer.get(p).values()];
    return {
      player: p, games: gs.length, score: meanCI(gs.map((g) => g.score)),
      wiped: gs.filter((g) => g.wiped_turn !== null).length,
      vsHold: p === "hold" ? null : paired(p, "hold"),
      vsShuffled: p.includes(":") || p === "hold" || p === "random" ? null : paired(p, `${p}:shuffled`),
      orders: +(gs.reduce((a, g) => a + g.orders_per_turn, 0) / gs.length).toFixed(1),
    };
  }).sort((a, b) => b.score.mean - a.score.mean);
  const verdict = (c) => !c ? "" : c.lo > 0 ? "better" : c.hi < 0 ? "worse" : "no difference";
  const lines = [
    `# Stage benchmark: ${plan.name || "run"}`, "",
    `${games.length} games: ${plan.seats.length} seats x ${plan.seeds.length} seeds x ${byPlayer.size} players, ${plan.turns} turns each, Open Doctrines ${readFileSync(path.join(web, "agent", "VERSION"), "utf8").trim()}.`,
    "Score = land share at the end minus at the start, percentage points (wiped out = ended on 0). Intervals are 95% bootstrap over games; \"vs\" columns are paired on the same seat and seed.",
    "This compares mappings we wrote, not animals. The one comparison about the wiring itself is each animal against its own shuffled copy.", "",
    "| player | games | mean score [95% CI] | wiped | vs hold | vs its shuffled wiring | orders/turn |",
    "|---|---|---|---|---|---|---|",
    ...rows.map((r) => `| ${r.player} | ${r.games} | ${ci(r.score)} | ${r.wiped}/${r.games} | ${r.vsHold ? `${ci(r.vsHold)} ${verdict(r.vsHold)}` : "—"} | ${r.vsShuffled ? `${ci(r.vsShuffled)} ${verdict(r.vsShuffled)}` : "—"} | ${r.orders} |`),
  ];
  return { rows, markdown: lines.join("\n") + "\n" };
}

// ---------------------------------------------------------------- driver
if (arg("one")) {
  playOne(JSON.parse(arg("one"))).then((r) => { process.stdout.write(JSON.stringify(r) + "\n"); process.exit(0); })
    .catch((e) => { process.stderr.write(String(e && e.stack || e) + "\n"); process.exit(1); });
} else {
  const plan = JSON.parse(readFileSync(arg("plan"), "utf8"));
  const out = arg("out", "data/bench/run.json"), jobs = +arg("jobs", "4");
  mkdirSync(path.dirname(out), { recursive: true });
  // Resumable: games already in the output are not played again.
  const done = existsSync(out) ? JSON.parse(readFileSync(out, "utf8")).games : [];
  const have = new Set(done.map((g) => `${g.player}|${g.seat}|${g.seed}`));
  const todo = [];
  for (const player of plan.players) for (const seat of plan.seats) for (const seed of plan.seeds)
    if (!have.has(`${player}|${seat}|${seed}`)) todo.push({ player, seat, seed, turns: plan.turns });
  // Big brains first, so the long games are not the ones left running alone.
  const weight = (p) => /drosophila_(female|male)|zebrafish/.test(p.player) ? 0 : 1;
  todo.sort((a, b) => weight(a) - weight(b));
  const games = [...done], failed = [];
  let next = 0, running = 0;
  const save = () => writeFileSync(out, JSON.stringify({ plan, games, failed }, null, 1));
  console.log(`${todo.length} games to play, ${done.length} already done, ${jobs} at a time`);
  await new Promise((resolve) => {
    const launch = () => {
      while (running < jobs && next < todo.length) {
        const job = todo[next++]; running++;
        const child = spawn(process.execPath, ["--max-old-space-size=6144", fileURLToPath(import.meta.url), "--one", JSON.stringify(job)], { stdio: ["ignore", "pipe", "pipe"] });
        let o = "", e = "";
        child.stdout.on("data", (d) => (o += d)); child.stderr.on("data", (d) => (e += d));
        child.on("close", (code) => {
          running--;
          if (code === 0) { const g = JSON.parse(o.trim().split("\n").pop()); games.push(g); console.log(`${games.length - done.length}/${todo.length}  ${g.player} ${g.seat} seed ${g.seed}: ${fmt(g.score)} (${g.seconds}s)`); }
          else { failed.push({ ...job, error: e.slice(-400) }); console.log(`FAILED ${job.player} ${job.seat} ${job.seed}: ${e.slice(-200)}`); }
          save();
          if (next >= todo.length && running === 0) resolve(); else launch();
        });
      }
      if (todo.length === 0) resolve();
    };
    launch();
  });
  const { markdown } = report(games, plan);
  writeFileSync(out.replace(/\.json$/, ".md"), markdown);
  console.log("\n" + markdown);
  if (failed.length) console.log(`${failed.length} games FAILED; see ${out}`);
}
