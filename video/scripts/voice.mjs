// Renders each beat with macOS `say`, converts to 48 kHz WAV in public/vo, and writes src/timeline.json.
import {execFileSync} from "node:child_process";
import {mkdirSync, writeFileSync, readFileSync} from "node:fs";
import {beats, VOICE, RATE} from "./beats.mjs";
const FPS = 30, PAD = {hook: 0.35, solution: 0.4, demo: 1.5, impact: 1.0, end: 1.8};
mkdirSync("public/vo", {recursive: true});
const manifest = JSON.parse(readFileSync("public/shots/manifest.json", "utf8"));
const byName = Object.fromEntries(manifest.map((m) => [m.name, m]));
const out = [];
for (const b of beats) {
  const aiff = `/tmp/bb_${b.id}.aiff`, wav = `public/vo/${b.id}.wav`;
  // `say` sometimes stalls and sometimes cuts a sentence short. Render until the longest take has been
  // produced twice, and keep that one.
  const dur = (f) => parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).toString());
  const takes = [];
  for (let k = 0; k < 8; k++) {
    const f = `/tmp/bb_${b.id}_${k}.aiff`;
    try { execFileSync("say", ["-v", VOICE, "-r", String(RATE), "-o", f, b.say], {timeout: 30000}); } catch { continue; }
    takes.push({f, d: dur(f)});
    const best = Math.max(...takes.map((t) => t.d));
    if (takes.filter((t) => Math.abs(t.d - best) < 0.02).length >= 2) break;
  }
  const best = takes.reduce((a, t) => (t.d > a.d ? t : a));
  execFileSync("cp", [best.f, aiff]);
  execFileSync("ffmpeg", ["-y", "-v", "error", "-i", aiff, "-ar", "48000", "-ac", "1", "-af", "loudnorm=I=-16:TP=-1.5", wav]);
  const sec = parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav]).toString());
  const shots = (b.shots || []).map((s) => s.typing
    ? {typing: true, frames: manifest.filter((m) => m.name.startsWith(s.typing + "_")).map((m) => m.file), click: manifest.find((m) => m.name.startsWith(s.typing + "_"))?.click, w: s.w ?? 0.55}
    : {file: byName[s.name].file, click: byName[s.name].click, focus: s.zoom ? byName[s.name].focus : undefined, w: s.w ?? 1});
  out.push({id: b.id, section: b.section, chip: b.chip, cap: b.cap ?? b.say, audio: `vo/${b.id}.wav`,
    audioFrames: Math.ceil(sec * FPS), frames: Math.ceil((sec + PAD[b.section] + (b.hold ?? 0)) * FPS), shots});
  console.log(b.id, sec.toFixed(2) + "s");
}
writeFileSync("src/timeline.json", JSON.stringify(out, null, 1));
const tot = (s) => out.filter((b) => b.section === s).reduce((a, b) => a + b.frames, 0) / FPS;
console.log("hook", tot("hook"), "solution", tot("solution"), "demo", tot("demo"), "impact", tot("impact"), "end", tot("end"),
  "total", out.reduce((a, b) => a + b.frames, 0) / FPS);
