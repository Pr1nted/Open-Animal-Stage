// Renders the trailer's text and end card as PNGs, in the page's own fonts
// (Big Shoulders Display, Figtree), through headless Chrome:
//   captions/NN.png  one per shot with a caption, transparent 1920x1080
//   hint.png         the corner hint ("Play it in your browser"), transparent
//   endcard.png      the three logos and the credit, opaque
//
//   node tools/trailer/overlays.mjs [--out out/trailer]
//
// Logos: Open Fly from ../Open-Fly/docs/brand, Open Animal Stage from
// docs/brand, Open Doctrines from ../OpenDoctrines/data/Icon (override with
// OPEN_FLY_DIR / OD_DIR). If this project's logo is missing, the end card
// falls back to a text wordmark and says so on stderr.
import { launch } from "./cdp.mjs";
import { SHOTS } from "./shots.mjs";
import { mkdirSync, writeFileSync, existsSync, copyFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i < 0 ? d : process.argv[i + 1]; };
const OUT = resolve(ROOT, arg("out", "out/trailer"));
const FLY = resolve(process.env.OPEN_FLY_DIR || join(ROOT, "../Open-Fly"));
const OD = resolve(process.env.OD_DIR || join(ROOT, "../OpenDoctrines"));
const work = join(OUT, "overlays"); mkdirSync(join(work, "captions"), { recursive: true });

// Copy the logos next to the HTML so the file:// page can read them.
const logos = {
  fly: [join(FLY, "docs/brand/open-fly-stacked-white.png"), join(FLY, "docs/itch/favicon/favicon-512.png")].find(existsSync),
  oas: [join(ROOT, "docs/brand/logo.png"), join(ROOT, "docs/brand/logo.svg")].find(existsSync),
  od: [join(OD, "data/Icon/icon.png"), join(OD, "packaging/web/favicon.png")].find(existsSync),
};
for (const [k, p] of Object.entries(logos)) if (p) copyFileSync(p, join(work, `${k}${p.slice(p.lastIndexOf("."))}`));
const src = (k) => logos[k] ? `${k}${logos[k].slice(logos[k].lastIndexOf("."))}` : null;
if (!logos.oas) console.error("WARNING: docs/brand/logo.png is missing; the end card uses a text wordmark. Re-run when the logo exists.");

const FONTS = `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800&family=Figtree:wght@400;500;600&display=block">`;
const BASE = `
  * { box-sizing: border-box; margin: 0; }
  html, body { width: 1920px; height: 1080px; background: transparent; overflow: hidden; }
  body { font-family: Figtree, "Helvetica Neue", Arial, sans-serif; color: #EDE6D6; -webkit-font-smoothing: antialiased; }`;

const caption = ([a, b]) => `<!doctype html><meta charset="utf-8">${FONTS}<style>${BASE}
  .shade { position: absolute; left: 0; bottom: 0; width: 1300px; height: 420px;
    background: radial-gradient(ellipse 900px 300px at 0% 100%, rgba(8,11,13,.5), rgba(8,11,13,0) 70%); }
  .cap { position: absolute; left: 112px; bottom: 118px; text-shadow: 0 2px 18px rgba(0,0,0,.55); }
  .rule { width: 56px; height: 4px; background: #F2B84B; border-radius: 2px; margin-bottom: 22px; }
  .a { font: 800 66px/1 "Big Shoulders Display", "Arial Narrow", sans-serif; letter-spacing: .01em; text-transform: uppercase; }
  .b { font: 500 36px/1.25 Figtree, sans-serif; color: #EDE6D6; opacity: .92; margin-top: 12px; }
</style><div class="shade"></div><div class="cap"><div class="rule"></div><div class="a">${a}</div><div class="b">${b}</div></div>`;

const hint = `<!doctype html><meta charset="utf-8">${FONTS}<style>${BASE}
  .hint { position: absolute; right: 64px; bottom: 58px; display: flex; align-items: center; gap: 16px; text-align: right;
    text-shadow: 0 1px 10px rgba(0,0,0,.6); }
  .t { font: 600 25px/1.2 Figtree, sans-serif; color: #EDE6D6; }
  .u { font: 500 21px/1.2 Figtree, sans-serif; color: #F2B84B; margin-top: 3px; letter-spacing: .02em; }
  .arrow { width: 46px; height: 46px; border-radius: 50%; border: 2px solid rgba(242,184,75,.85); display: grid; place-items: center;
    color: #F2B84B; font: 600 26px/1 Figtree, sans-serif; background: rgba(12,17,19,.35); }
</style><div class="hint"><div><div class="t">Play it in your browser</div><div class="u">pr1nted.itch.io</div></div><div class="arrow">&rarr;</div></div>`;

const card = `<!doctype html><meta charset="utf-8">${FONTS}<style>${BASE}
  body { background: #0C1113; }
  .glow { position: absolute; inset: 0; background: radial-gradient(ellipse 1100px 520px at 50% 46%, rgba(111,183,174,.10), rgba(12,17,19,0) 70%); }
  .row { position: absolute; left: 0; right: 0; top: 300px; display: grid; grid-template-columns: 1fr 1.55fr 1fr; align-items: start; padding: 0 110px; gap: 40px; }
  .col { display: grid; justify-items: center; align-items: center; grid-template-rows: 16px 200px auto; gap: 26px; text-align: center; }
  img { image-rendering: pixelated; display: block; }
  .fly img { width: 300px; }
  .oas img { width: 640px; }
  .oas .word { font: 800 92px/0.9 "Big Shoulders Display", sans-serif; text-transform: uppercase; }
  .oas .word span { color: #F2B84B; }
  .od img { width: 190px; height: 190px; border-radius: 22px; box-shadow: 0 10px 40px rgba(0,0,0,.5); image-rendering: auto; }
  .lab { font: 500 24px/1.3 Figtree, sans-serif; color: #8F9A97; }
  .lab b { color: #EDE6D6; font-weight: 600; }
  .cta { font: 600 27px/1.3 Figtree, sans-serif; color: #EDE6D6; }
  .cta em { font-style: normal; color: #F2B84B; }
  .sister { font: 600 15px/1 Figtree, sans-serif; letter-spacing: .18em; text-transform: uppercase; color: #8F9A97; }
  .made { position: absolute; left: 0; right: 0; bottom: 96px; text-align: center; font: 500 26px/1 Figtree, sans-serif; color: #8F9A97; letter-spacing: .04em; }
  .made b { color: #EDE6D6; font-weight: 600; }
  .url { position: absolute; left: 0; right: 0; bottom: 148px; text-align: center; font: 600 30px/1 Figtree, sans-serif; color: #F2B84B; letter-spacing: .03em; }
</style><div class="glow"></div><div class="row">
  <div class="col fly"><div class="sister">Sister project</div>${src("fly") ? `<img src="${src("fly")}" alt="Open Fly">` : `<div class="word">Open Fly</div>`}<div class="lab">One fly brain plays<br>Open Doctrines</div></div>
  <div class="col oas"><div class="sister">&nbsp;</div>${src("oas") ? `<img src="${src("oas")}" alt="Open Animal Stage">` : `<div class="word">Open Animal <span>Stage</span></div>`}<div class="lab">Mapped brains, live in your browser</div></div>
  <div class="col od"><div class="sister">The game</div>${src("od") ? `<img src="${src("od")}" alt="Open Doctrines">` : ""}<div class="cta">Open Doctrines &mdash;<br><em>Play and rate now</em></div></div>
</div><div class="url">pr1nted.itch.io</div><div class="made">Made by <b>Pr1nted</b></div>`;

const p = await launch({});
try {
  await p.send("Emulation.setDefaultBackgroundColorOverride", { color: { r: 0, g: 0, b: 0, a: 0 } });
  const shoot = async (html, file) => {
    const f = join(work, "page.html"); writeFileSync(f, html);
    await p.goto(pathToFileURL(f).href);
    await p.eval(`document.fonts.ready.then(() => Promise.all([...document.images].map((i) => i.complete ? 1 : new Promise((r) => { i.onload = i.onerror = r; }))))`);
    const fams = await p.eval(`[...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family).join(",")`);
    writeFileSync(file, await p.png({ optimizeForSpeed: false }));
    return fams;
  };
  let fams = "";
  for (const [k, s] of SHOTS.entries()) if (s.caption) fams = await shoot(caption(s.caption), join(work, "captions", `${String(k).padStart(2, "0")}.png`));
  await shoot(hint, join(work, "hint.png"));
  await p.send("Emulation.setDefaultBackgroundColorOverride", {});
  await shoot(card, join(work, "endcard.png"));
  console.log(`overlays in ${work} (fonts loaded: ${fams || "none -- system fallback"})`);
} finally {
  await p.close();
}
