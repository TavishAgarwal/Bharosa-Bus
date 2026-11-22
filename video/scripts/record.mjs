// Records the prototype demo as ONE continuous take of the live app (no cuts, no stills).
// Headless Chrome is driven with real mouse/keyboard input over the DevTools protocol; a cursor is drawn
// inside the page so it is part of the recording. Every action is scheduled against the narration
// (src/timeline.json, demo beats), so the voice lines up with what happens on screen.
// Output: public/rec/demo.mp4 (1920x1080, 30 fps) and src/zoom.json (camera zoom windows).
// Usage: node scripts/record.mjs [base-url]   (default http://127.0.0.1:8010; needs `make serve` running)
import {spawn, execFileSync} from "node:child_process";
import {mkdtempSync, writeFileSync, mkdirSync, readFileSync, rmSync, symlinkSync} from "node:fs";
import {tmpdir} from "node:os";
import path from "node:path";

const BASE = process.argv[2] || "http://127.0.0.1:8010";
const OUT = path.resolve("public/rec"), FR = path.join(tmpdir(), "bb_rec_frames");
rmSync(FR, {recursive: true, force: true}); mkdirSync(FR, {recursive: true}); mkdirSync(OUT, {recursive: true});
const W = 1440, H = 810, DPR = 1920 / 1440, FPS = 30;
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", PORT = 9334;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// beat start times (s) inside the demo section
const tl = JSON.parse(readFileSync("src/timeline.json", "utf8")).filter((b) => b.section === "demo");
const T = {}; let acc = 0;
for (const b of tl) { T[b.id] = acc; acc += b.frames / FPS; }
const END = acc;

const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${mkdtempSync(path.join(tmpdir(), "bbrec-"))}`,
  "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", `--window-size=${W},${H}`, "about:blank"], {stdio: "ignore"});
let ws, id = 0;
const pending = new Map(), listeners = [];
async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const page = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((t) => t.type === "page");
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
async function idle(max = 6000) {
  for (let t = 0; t < max; t += 120) {
    const busy = await js(`(()=>{const t=[...document.querySelectorAll('.leaflet-tile')].filter(x=>!x.classList.contains('leaflet-tile-loaded')).length;const o=document.getElementById('out');return t+(o&&/Planning/.test(o.textContent)?1:0);})()`).catch(() => 1);
    if (!busy) return;
    await sleep(120);
  }
}

// cursor drawn in the page; its position survives page loads via sessionStorage
const CURSOR = `(()=>{const mk=()=>{if(document.getElementById('__cur'))return;const c=document.createElement('div');c.id='__cur';
c.style.cssText='position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:30px;height:30px;will-change:transform';
c.innerHTML='<svg width="30" height="30" viewBox="0 0 24 24" style="filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))"><path d="M4 2 L4 19 L8.5 14.8 L11.4 21.4 L14.2 20.2 L11.3 13.7 L17.5 13.7 Z" fill="#111" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>';
document.documentElement.appendChild(c);const p=JSON.parse(sessionStorage.__cp||'[900,450]');c.style.transform='translate('+(p[0]-4)+'px,'+(p[1]-2)+'px)';};
window.__move=(x,y)=>{mk();const c=document.getElementById('__cur');c.style.transform='translate('+(x-4)+'px,'+(y-2)+'px)';sessionStorage.__cp=JSON.stringify([x,y]);};
window.__ripple=(x,y)=>{const r=document.createElement('div');r.style.cssText='position:fixed;z-index:2147483646;pointer-events:none;left:'+(x-24)+'px;top:'+(y-24)+'px;width:48px;height:48px;border-radius:50%;border:3px solid #1f6feb;opacity:.9;transform:scale(.3);transition:transform .45s ease-out,opacity .45s ease-out';document.documentElement.appendChild(r);requestAnimationFrame(()=>requestAnimationFrame(()=>{r.style.transform='scale(1.3)';r.style.opacity='0';}));setTimeout(()=>r.remove(),600);};
document.addEventListener('mousemove',e=>window.__move(e.clientX,e.clientY),true);
document.addEventListener('mousedown',e=>window.__ripple(e.clientX,e.clientY),true);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mk);else mk();})()`;

let cx = 900, cy = 450;
const ease = (p) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2);
async function moveTo(x, y, ms = 550) {
  const x0 = cx, y0 = cy, n = Math.max(6, Math.round(ms / 16));
  for (let i = 1; i <= n; i++) {
    const p = ease(i / n);
    cx = x0 + (x - x0) * p; cy = y0 + (y - y0) * p;
    await send("Input.dispatchMouseEvent", {type: "mouseMoved", x: cx, y: cy});
    await sleep(ms / n);
  }
}
async function box(sel) {
  const r = await js(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});if(!e)return null;const b=e.getBoundingClientRect();return [b.x,b.y,b.width,b.height];})()`);
  if (!r) throw new Error("not found: " + sel);
  return r;
}
// scroll the panel with the mouse wheel until the element is fully on screen
async function wheelTo(sel, pane = "#out") {
  const [px, py, pw, ph] = await box(pane);
  await moveTo(px + pw * 0.55, py + ph * 0.6, 450);
  for (let i = 0; i < 30; i++) {
    const [, y, , h] = await box(sel);
    const bottom = Math.min(H, py + ph) - 24;
    if (y + h <= bottom && y >= py) break;
    const dy = y + h > bottom ? Math.min(120, y + h - bottom + 10) : -Math.min(120, py - y + 10);
    await send("Input.dispatchMouseEvent", {type: "mouseWheel", x: cx, y: cy, deltaX: 0, deltaY: dy});
    await sleep(70);
  }
  await sleep(250);
}
async function pointAt(sel, ms) { const [x, y, w, h] = await box(sel); await moveTo(x + w / 2, y + h / 2, ms); }
async function click(sel, ms) {
  await pointAt(sel, ms); await sleep(90);
  await send("Input.dispatchMouseEvent", {type: "mousePressed", x: cx, y: cy, button: "left", clickCount: 1});
  await sleep(70);
  await send("Input.dispatchMouseEvent", {type: "mouseReleased", x: cx, y: cy, button: "left", clickCount: 1});
}
// native <select> popups are not drawn by headless Chrome: point and click the control, then pick the option
async function choose(sel, value, ms) {
  await pointAt(sel, ms); await sleep(90);
  await js(`window.__ripple(${cx},${cy})`); await sleep(260);
  await js(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});e.focus();e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
}
async function type(text, per = 75) {
  for (const ch of text) { await send("Input.insertText", {text: ch}); await sleep(per); }
}
async function key(k, code) {
  await send("Input.dispatchKeyEvent", {type: "keyDown", key: k, code, windowsVirtualKeyCode: k === "Escape" ? 27 : 13});
  await send("Input.dispatchKeyEvent", {type: "keyUp", key: k, code, windowsVirtualKeyCode: k === "Escape" ? 27 : 13});
}
async function navClick(text) {
  const loaded = new Promise((r) => { const l = (m) => { if (m.method === "Page.loadEventFired") { listeners.splice(listeners.indexOf(l), 1); r(); } }; listeners.push(l); });
  await click(`header a[href="${text}"], nav a[href="${text}"], a[href="${text}"]`);
  await loaded; await idle();
}

// ---------- recording ----------
let t0 = 0;
const frames = [];
const now = () => Date.now() / 1000 - t0;
async function until(t) { const d = t - now(); if (d > 0) await sleep(d * 1000); }
const log = (id) => console.log(id.padEnd(4), "planned", T[id].toFixed(2), "actual", now().toFixed(2));
const zoom = [];
async function zoomOn(sel, from, to, clip) {
  let [x, y, w, h] = await box(sel);
  if (clip) { // keep only the part visible inside the scroll pane
    const [, cy0, , ch] = await box(clip);
    const y1 = Math.max(y, cy0), y2 = Math.min(y + h, cy0 + ch, H);
    y = y1; h = y2 - y1;
  }
  zoom.push({from, to, box: [x * DPR, y * DPR, w * DPR, h * DPR]});
}

await connect();
await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", {width: W, height: H, deviceScaleFactor: DPR, mobile: false});
await send("Page.addScriptToEvaluateOnNewDocument", {source: CURSOR});
const first = new Promise((r) => { const l = (m) => { if (m.method === "Page.loadEventFired") { listeners.splice(listeners.indexOf(l), 1); r(); } }; listeners.push(l); });
await send("Page.navigate", {url: BASE + "/"});
await first; await idle(); await sleep(2500); await idle(); // live mode plans Connaught Place -> Anand Vihar on load
await send("Input.dispatchMouseEvent", {type: "mouseMoved", x: cx, y: cy});

listeners.push(async (m) => {
  if (m.method !== "Page.screencastFrame") return;
  const t = Date.now() / 1000 - t0, f = path.join(FR, `f${String(frames.length).padStart(5, "0")}.jpg`);
  writeFileSync(f, Buffer.from(m.params.data, "base64"));
  frames.push({f, t});
  send("Page.screencastFrameAck", {sessionId: m.params.sessionId}).catch(() => {});
});
t0 = Date.now() / 1000;
await send("Page.startScreencast", {format: "jpeg", quality: 92, everyNthFrame: 1});

// d1: sample trip, weekday 18:00
await until(T.d1 + 0.4); log("d1");
await click('#mode button[data-m="demo"]', 700);
await until(T.d1 + 1.8); await choose("#trip", "Rohini Sector 22 → Nehru Place");
await until(T.d1 + 3.2); await choose("#time", "weekday 18:00"); await idle();
await until(T.d1 + 6.0); await moveTo(1000, 430, 1200);
// d2: Balanced
await until(T.d2 + 0.3); log("d2");
await click('#rank button[data-w="0.5"]'); await idle();
await until(T.d2 + 3.5); await pointAt(".card.sel .ctitle, .card.sel", 700);
// d3: open "Why this estimate?"
await until(T.d3 + 0.2); log("d3");
await wheelTo(".card.sel details summary");
await click(".card.sel details summary", 400);
await sleep(200);
await wheelTo(".card.sel details");
await sleep(300);
await zoomOn(".card.sel details", T.d3 + 1.4, T.d4 - 0.5);
// d4: Hindi
await until(T.d4 + 0.1); log("d4");
await choose("#lang", "hi", 550); await sleep(400);
await zoomOn(".card.sel", now() + 0.3, T.d5 - 0.3, "#out");
// d5: same corridor, two times of day
await until(T.d5 + 0.1); log("d5");
await choose("#lang", "en", 450);
await click('#rank button[data-w="0"]', 450);
await until(T.d5 + 1.6); await choose("#trip", "Anand Vihar → Connaught Place", 500);
await until(T.d5 + 2.8); await choose("#time", "weekday 08:30", 450); await idle();
await until(T.d5 + 5.6); await moveTo(1000, 430, 900);
await until(T.d5 + 7.0); await choose("#time", "weekday 18:00", 600); await idle();
// d6: live search, any stop
await until(T.d6 + 0.2); log("d6");
await click('#mode button[data-m="live"]', 600);
await sleep(500);
await click("#cf", 450); await js(`document.getElementById('cf').select()`); await type("Rajouri Garden"); await key("Escape", "Escape");
await click("#ct", 400); await js(`document.getElementById('ct').select()`); await type("Lajpat Nagar"); await key("Escape", "Escape");
await choose("#ctime", "08:30", 400);
await click("#cgo", 450); await idle();
await until(T.d6 + 7.5); await moveTo(1000, 430, 900);
// d6n: after dark, the ranking adjusts by itself
await until(T.d6n + 0.2); log("d6n");
await click("#cf", 500); await js(`document.getElementById('cf').select()`); await type("Connaught Place", 60); await key("Escape", "Escape");
await click("#ct", 400); await js(`document.getElementById('ct').select()`); await type("Anand Vihar", 60); await key("Escape", "Escape");
await choose("#ctime", "21:30", 400);
await click("#cgo", 450); await idle();
await until(T.d6n + 7.0); await pointAt('#rank button[aria-pressed="true"]', 700);
await until(T.d6n + 10.0); await pointAt(".card.sel .tag", 700);
await zoomOn(".card.sel", T.d6n + 10.6, T.d7 - 0.4, "#out");
// d7: route map, 717A
await until(T.d7 + 0.2); log("d7");
await navClick("routes.html");
await click("#q", 500); await type("717AUP", 90);
await click('#bands button[data-v="1"]', 500); await idle();
await until(T.d7 + 5.8); await click('#bands button[data-v="3"]', 600); await idle();
await until(T.d7 + 8.4); await click('#days button[data-v="weekend"]', 600); await idle();
// d8: operators
await until(T.d8 + 0.2); log("d8");
await navClick("operators.html");
await until(T.d8 + 3.0); await moveTo(700, 380, 1000);
await until(T.d8 + 10.5); await click('#view button[data-v="cr"]', 700); await idle();
await until(END + 0.3);
console.log("end", "planned", END.toFixed(2), "actual", now().toFixed(2));
await send("Page.stopScreencast");
ws.close(); chrome.kill();

// frames arrive only when the screen changes: for each output frame, use the latest frame captured by then
const SEQ = path.join(FR, "seq"); mkdirSync(SEQ, {recursive: true});
const n = Math.ceil(END * FPS);
let j = 0;
for (let k = 0; k < n; k++) {
  const t = k / FPS;
  while (j + 1 < frames.length && frames[j + 1].t <= t) j++;
  symlinkSync(frames[j].f, path.join(SEQ, `s${String(k).padStart(5, "0")}.jpg`));
}
execFileSync("ffmpeg", ["-y", "-v", "error", "-framerate", String(FPS), "-i", path.join(SEQ, "s%05d.jpg"),
  "-vf", "scale=1920:1080:flags=lanczos", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "16", path.join(OUT, "demo.mp4")]);
writeFileSync("src/zoom.json", JSON.stringify(zoom, null, 1));
console.log("frames", frames.length, "size", execFileSync("ffprobe", ["-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0", frames[0].f]).toString().trim(), "-> public/rec/demo.mp4", n, "frames");
