// Drives the live Bharosa Bus app (make serve / bharosa.serve) in headless Chrome over the DevTools protocol
// and saves 1920x1080 screenshots plus where each click landed, for the Remotion demo scene.
// Usage: node scripts/capture.mjs [base-url]   (default http://127.0.0.1:8010)
import {spawn} from "node:child_process";
import {mkdtempSync, writeFileSync, mkdirSync} from "node:fs";
import {tmpdir} from "node:os";
import path from "node:path";

const BASE = process.argv[2] || "http://127.0.0.1:8010";
const OUT = path.resolve("public/shots");
mkdirSync(OUT, {recursive: true});
const W = 1440, H = 810, DPR = 1920 / 1440;
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${mkdtempSync(path.join(tmpdir(), "bbcap-"))}`,
  "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", `--window-size=${W},${H}`, "about:blank"], {stdio: "ignore"});

let ws, id = 0;
const pending = new Map(), listeners = [];
async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); break; }
    } catch {}
    await sleep(200);
  }
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { const {res, rej} = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(m.error.message)) : res(m.result); }
    else if (m.method) listeners.forEach((l) => l(m));
  });
}
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, {res, rej}); ws.send(JSON.stringify({id: i, method, params})); });
async function js(expr) {
  const r = await send("Runtime.evaluate", {expression: expr, awaitPromise: true, returnByValue: true});
  if (r.exceptionDetails) throw new Error(expr.slice(0, 80) + " -> " + JSON.stringify(r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result.value;
}
async function settle(extra = 900) {
  // wait for the map tiles and any planner fetch to finish
  for (let i = 0; i < 60; i++) {
    const busy = await js(`(()=>{const t=[...document.querySelectorAll('.leaflet-tile')].filter(x=>!x.classList.contains('leaflet-tile-loaded')).length;const o=document.getElementById('out');return t+(o&&/Planning/.test(o.textContent)?1:0);})()`);
    if (!busy) break;
    await sleep(150);
  }
  await sleep(extra);
}
async function nav(url) {
  const loaded = new Promise((r) => { const l = (m) => { if (m.method === "Page.loadEventFired") { listeners.splice(listeners.indexOf(l), 1); r(); } }; listeners.push(l); });
  await send("Page.navigate", {url: BASE + url});
  await loaded;
  await settle(1500);
}
// centre of an element, in screenshot pixels
async function at(sel) {
  const r = await js(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});if(!e)return null;e.scrollIntoView({block:'nearest'});const b=e.getBoundingClientRect();return [b.x+b.width/2,b.y+b.height/2,b.x,b.y,b.width,b.height];})()`);
  if (!r) throw new Error("not found: " + sel);
  return {x: Math.round(r[0] * DPR), y: Math.round(r[1] * DPR), box: r.slice(2).map((v) => Math.round(v * DPR))};
}
const manifest = [];
async function shot(name, extra = {}) {
  const {data} = await send("Page.captureScreenshot", {format: "png"});
  writeFileSync(path.join(OUT, name + ".png"), Buffer.from(data, "base64"));
  manifest.push({name, file: `shots/${name}.png`, ...extra});
  console.log("shot", name);
}
async function click(sel) { const p = await at(sel); await js(`document.querySelector(${JSON.stringify(sel)}).click()`); return p; }
async function choose(sel, value) {
  const p = await at(sel);
  await js(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  return p;
}
async function typeInto(sel, text, prefix) {
  const p = await at(sel);
  await js(`document.querySelector(${JSON.stringify(sel)}).value=''`);
  for (let i = 1; i <= text.length; i++) {
    await js(`document.querySelector(${JSON.stringify(sel)}).value=${JSON.stringify(text.slice(0, i))}`);
    if (i % 2 === 0 || i === text.length) await shot(`${prefix}_${String(i).padStart(2, "0")}`, {typing: true, click: i <= 2 ? p : undefined});
  }
  return p;
}

await connect();
await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", {width: W, height: H, deviceScaleFactor: DPR, mobile: false});

// --- Planner: sample trip, fastest vs most comfortable ---
await nav("/");
await settle(2500); // live mode plans CP -> AV on load
await click('#mode button[data-m="demo"]');
await choose("#trip", "Rohini Sector 22 → Nehru Place");
await choose("#time", "weekday 18:00");
await settle(1800);
await shot("p01_fastest");
let c = await click('#rank button[data-w="0.5"]'); await settle(1800);
await shot("p02_comfort", {click: c});
c = await at(".card.sel details summary");
await js(`(()=>{const d=document.querySelector('.card.sel details');d.open=true;d.scrollIntoView({block:'end'});})()`); await settle(500);
const why = await at(".card.sel details");
await shot("p03_why", {click: c, focus: why.box});
c = await choose("#lang", "hi"); await settle(900);
await js(`document.querySelector('.card.sel details').open=false; document.getElementById('out').scrollTop=0`); await settle(400);
const hc = await at(".card.sel");
await shot("p04_hindi", {click: c, focus: hc.box});
await choose("#lang", "en");
await click('#rank button[data-w="0"]');
// --- Direction and time of day on one corridor ---
c = await choose("#trip", "Anand Vihar → Connaught Place");
await choose("#time", "weekday 08:30"); await settle(1800);
await shot("p05_av_cp_0830", {click: c});
c = await choose("#time", "weekday 18:00"); await settle(1800);
await shot("p06_av_cp_1800", {click: c});
// --- Live search, any stop to any stop ---
c = await click('#mode button[data-m="live"]'); await settle(1200);
await shot("p07_live", {click: c});
await typeInto("#cf", "Rajouri Garden", "p08_from");
await typeInto("#ct", "Lajpat Nagar", "p09_to");
await js(`document.getElementById('ctime').value='08:30'`);
c = await click("#cgo"); await sleep(400); await settle(2200);
await shot("p10_live_result", {click: c});

// --- Route map ---
await nav("/routes.html?route=717AUP&day=weekday&band=1");
await shot("r01_717_am");
c = await click('#bands button[data-v="3"]'); await settle(1500);
await shot("r02_717_pm", {click: c});
c = await click('#days button[data-v="weekend"]'); await settle(1500);
await shot("r03_717_pm_weekend", {click: c});

// --- Operators ---
await nav("/operators.html");
await shot("o01_extra_bus");
c = await click('#view button[data-v="crowded"]').catch(async () => click("#view button:nth-child(2)")); await settle(1500);
await shot("o02_crowded", {click: c});

writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 1));
ws.close(); chrome.kill();
console.log("done", manifest.length, "shots");
