// Checks ?record end to end in headless Chrome: runs the auto tour (T) to its
// end and a short manual recording (R ... R), and reports the downloaded files.
//   node tools/trailer/record_test.mjs [http://127.0.0.1:8110/] [download dir]
import { launch } from "./cdp.mjs";
import { mkdirSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
const base = process.argv[2] || "http://127.0.0.1:8110/";
const dir = resolve(process.argv[3] || "out/record-test"); mkdirSync(dir, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const p = await launch({ downloads: dir });
await p.goto(`${base}?record`);
const key = async (code, key) => {
  for (const type of ["keyDown", "keyUp"]) await p.send("Input.dispatchKeyEvent", { type, code, key, windowsVirtualKeyCode: key.toUpperCase().charCodeAt(0) });
};
for (let i = 0; i < 120; i++) { if (/turn [2-9]/.test(await p.eval(`document.getElementById("nowTitle").textContent`))) break; await sleep(1000); }
await p.eval(`document.getElementById("stage").focus()`);
await key("KeyT", "t");
const t0 = Date.now();
await sleep(9000);
writeFileSync(join(dir, "during-tour.png"), await p.png());
while (await p.eval(`window.__recUi.recording`)) { await sleep(1000); if (Date.now() - t0 > 180000) break; }
console.log(`tour recorded for ${((Date.now() - t0) / 1000).toFixed(1)} s`);
await sleep(3000);
console.log("last:", JSON.stringify(await p.eval(`window.__recLast`)));
await key("KeyR", "r"); await sleep(5000); await key("KeyR", "r"); await sleep(3000);
console.log("last:", JSON.stringify(await p.eval(`window.__recLast`)));
await p.close();
for (const f of readdirSync(dir)) console.log(f, statSync(join(dir, f)).size);
