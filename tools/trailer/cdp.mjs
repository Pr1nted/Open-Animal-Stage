// A minimal headless-Chrome driver over the DevTools protocol, with nothing to
// install: Node 22's built-in WebSocket and fetch, and the Chrome already on
// the machine. Used by capture.mjs, overlays.mjs and record_test.mjs.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const CHROME = process.env.CHROME || [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
].find((p) => existsSync(p));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// gl: "gpu" (Metal through ANGLE on a Mac) or "swiftshader" (software, slow,
// but works anywhere).
export async function launch({ width = 1920, height = 1080, gl = "gpu", downloads = null } = {}) {
  if (!CHROME) throw new Error("no Chrome found; set CHROME=/path/to/chrome");
  const profile = mkdtempSync(join(tmpdir(), "oas-chrome-"));
  const glFlags = gl === "swiftshader" ? ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
    : process.platform === "darwin" ? ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] : ["--enable-gpu", "--ignore-gpu-blocklist"];
  const proc = spawn(CHROME, [
    "--headless=new", `--user-data-dir=${profile}`, "--remote-debugging-port=0", "--no-first-run", "--no-default-browser-check",
    "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
    "--autoplay-policy=no-user-gesture-required", "--hide-scrollbars", "--mute-audio",
    `--window-size=${width},${height}`, ...glFlags, "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });
  let port = null;
  for (let i = 0; i < 200 && !port; i++) {
    const f = join(profile, "DevToolsActivePort");
    if (existsSync(f)) port = +readFileSync(f, "utf8").split("\n")[0];
    else await sleep(50);
  }
  if (!port) throw new Error("Chrome did not open a DevTools port");
  const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const pageInfo = list.find((t) => t.type === "page");
  const page = await connect(pageInfo.webSocketDebuggerUrl);
  await page.send("Page.enable"); await page.send("Runtime.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
  if (downloads) {
    const browser = await connect((await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()).webSocketDebuggerUrl);
    await browser.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads, eventsEnabled: true });
    page.browser = browser;
  }
  page.close = async () => {
    try { proc.kill("SIGTERM"); } catch (_) { /* gone */ }
    await sleep(300);
    try { rmSync(profile, { recursive: true, force: true }); } catch (_) { /* busy */ }
  };
  page.proc = proc;
  return page;
}

export async function connect(url) {
  const ws = new WebSocket(url);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("DevTools socket failed")); });
  let id = 0; const waiting = new Map(), handlers = new Map();
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && waiting.has(m.id)) { const { res, rej } = waiting.get(m.id); waiting.delete(m.id); m.error ? rej(new Error(m.error.message)) : res(m.result); }
    else if (m.method) (handlers.get(m.method) || []).forEach((f) => f(m.params));
  };
  const self = {
    send: (method, params = {}) => new Promise((res, rej) => { const i = ++id; waiting.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); }),
    on: (method, f) => { if (!handlers.has(method)) handlers.set(method, []); handlers.get(method).push(f); },
    // Evaluate an expression in the page; promises are awaited.
    async eval(expr) {
      const r = await self.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(`${r.exceptionDetails.text} ${r.exceptionDetails.exception ? r.exceptionDetails.exception.description : ""}`);
      return r.result.value;
    },
    async goto(url) { const loaded = new Promise((r) => self.on("Page.loadEventFired", r)); await self.send("Page.navigate", { url }); await loaded; },
    async png(opts = {}) { const r = await self.send("Page.captureScreenshot", { format: "png", optimizeForSpeed: true, ...opts }); return Buffer.from(r.data, "base64"); },
    ws,
  };
  return self;
}
