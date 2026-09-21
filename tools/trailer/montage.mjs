// Cuts the captured shots to the music with ffmpeg: crossfades on bar lines,
// captions, the corner hint, the end card; 1920x1080, 30 fps, H.264 + AAC.
//
//   node tools/trailer/montage.mjs [--out out/trailer]
//
// Reads out/trailer/{timeline.json, frames/, music.wav, overlays/} and writes
// out/trailer/oas-trailer.mp4.
import { spawnSync } from "node:child_process";
import { readFileSync, existsSync, readdirSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i < 0 ? d : process.argv[i + 1]; };
const OUT = resolve(ROOT, arg("out", "out/trailer"));
const TL = JSON.parse(readFileSync(join(OUT, "timeline.json"), "utf8"));
const FFMPEG = process.env.FFMPEG || "ffmpeg";
const f3 = (x) => x.toFixed(3);

const inputs = [], chains = [];
const input = (...a) => { inputs.push(...a); return inputs.filter((x) => x === "-i").length - 1; };

// Shots, each filmed for its length plus one crossfade.
const frames = readdirSync(join(OUT, "frames"));
const shotIn = TL.shots.map((s, k) => {
  const dir = frames.find((d) => d === `${String(k).padStart(2, "0")}-${s.name}`);
  if (!dir) throw new Error(`no frames for shot ${k} (${s.name}); run capture.mjs`);
  return input("-framerate", String(TL.fps), "-i", join(OUT, "frames", dir, "%05d.png"));
});
const cardIn = input("-loop", "1", "-framerate", String(TL.fps), "-t", f3(TL.endCard.dur + TL.xfade), "-i", join(OUT, "overlays", "endcard.png"));
const hintIn = input("-loop", "1", "-framerate", String(TL.fps), "-t", f3(TL.endCard.start), "-i", join(OUT, "overlays", "hint.png"));
const capIn = TL.shots.map((s, k) => {
  const f = join(OUT, "overlays", "captions", `${String(k).padStart(2, "0")}.png`);
  return s.caption && existsSync(f) ? input("-loop", "1", "-framerate", String(TL.fps), "-t", f3(s.dur - 0.5), "-i", f) : null;
});
const musicIn = input("-i", join(OUT, "music.wav"));

// Crossfade chain: the k-th fade starts where shot k starts in the cut.
const norm = (i) => `[${i}:v]settb=AVTB,setsar=1,fps=${TL.fps},format=yuv420p`;
shotIn.forEach((i, k) => chains.push(`${norm(i)}[s${k}]`));
chains.push(`${norm(cardIn)}[card]`);
let last = "s0";
for (let k = 1; k < TL.shots.length; k++) {
  chains.push(`[${last}][s${k}]xfade=transition=fade:duration=${f3(TL.xfade)}:offset=${f3(TL.shots[k].start)}[x${k}]`);
  last = `x${k}`;
}
chains.push(`[${last}][card]xfade=transition=fade:duration=${f3(TL.xfade)}:offset=${f3(TL.endCard.start)}[cut]`);
// Fade up from black at the start and down to black at the very end.
chains.push(`[cut]fade=t=in:st=0:d=1.2,fade=t=out:st=${f3(TL.total - 1.2)}:d=1.2,format=yuva420p[base0]`);

// Captions: in 0.35 s after their cut, out before the next crossfade.
let cur = "base0", n = 0;
TL.shots.forEach((s, k) => {
  const i = capIn[k]; if (i == null) return;
  const d = s.dur - 0.5, t0 = s.start + 0.35;
  chains.push(`[${i}:v]format=rgba,fade=t=in:st=0:d=0.45:alpha=1,fade=t=out:st=${f3(d - 0.5)}:d=0.5:alpha=1,setpts=PTS-STARTPTS+${f3(t0)}/TB[c${k}]`);
  chains.push(`[${cur}][c${k}]overlay=0:0:eof_action=pass:format=auto[o${n}]`); cur = `o${n++}`;
});
// The corner hint: fades in after the opening, stays, at 70% opacity, until the end card.
const hs = 4.5, he = TL.endCard.start;
chains.push(`[${hintIn}:v]format=rgba,colorchannelmixer=aa=0.72,fade=t=in:st=${f3(hs)}:d=1.2:alpha=1,fade=t=out:st=${f3(he - 0.7)}:d=0.7:alpha=1,setpts=PTS-STARTPTS[hint]`);
chains.push(`[${cur}][hint]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]`);
// Music: trimmed to the picture, the last second and a half faded.
chains.push(`[${musicIn}:a]atrim=0:${f3(TL.total)},afade=t=out:st=${f3(TL.total - 1.6)}:d=1.6[a]`);

const out = join(OUT, "oas-trailer.mp4");
const args = ["-y", "-v", "error", ...inputs, "-filter_complex", chains.join(";\n"), "-map", "[v]", "-map", "[a]",
  "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-r", String(TL.fps), "-profile:v", "high",
  "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f3(TL.total), out];
const r = spawnSync(FFMPEG, args, { stdio: "inherit" });
if (r.status !== 0) { console.error("ffmpeg failed"); process.exit(1); }
console.log(`${out}: ${TL.total.toFixed(2)} s`);
