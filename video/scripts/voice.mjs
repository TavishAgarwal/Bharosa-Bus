// Renders each beat to speech, converts to 48 kHz WAV in public/vo, and writes src/timeline.json.
// Default engine is macOS `say`. With ELEVENLABS_API_KEY set, uses ElevenLabs (ELEVEN_VOICE picks the voice id).
// ElevenLabs takes are cached in /tmp by text, so re-running does not spend characters again.
import {execFileSync} from "node:child_process";
import {mkdirSync, writeFileSync, readFileSync, existsSync} from "node:fs";
import {createHash} from "node:crypto";
import {beats, VOICE, RATE} from "./beats.mjs";
const FPS = 30, PAD = {hook: 0.35, solution: 0.4, demo: 1.5, impact: 1.0, end: 1.8};
mkdirSync("public/vo", {recursive: true});
const KEY = process.env.ELEVENLABS_API_KEY, EVOICE = process.env.ELEVEN_VOICE || "onwK4e9ZLuTAKqWW03F9"; // Daniel
async function eleven(b, dst) {
  const h = createHash("sha1").update(EVOICE + b.say).digest("hex").slice(0, 12), cache = `/tmp/bb_el_${h}.mp3`;
  if (!existsSync(cache)) {
    const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${EVOICE}?output_format=mp3_44100_128`, {
      method: "POST", headers: {"xi-api-key": KEY, "Content-Type": "application/json"},
      body: JSON.stringify({text: b.say, model_id: "eleven_multilingual_v2",
        voice_settings: {stability: 0.5, similarity_boost: 0.75, style: 0.15, use_speaker_boost: true, speed: 1.0}})});
    if (!r.ok) throw new Error(`ElevenLabs ${r.status}: ${await r.text()}`);
    writeFileSync(cache, Buffer.from(await r.arrayBuffer()));
  }
  execFileSync("cp", [cache, dst]);
}
// Sarvam AI (Indian voices). SARVAM_API_KEY turns it on; SARVAM_MODEL / SARVAM_SPEAKER / SARVAM_PACE tune it.
const SKEY = process.env.SARVAM_API_KEY, SMODEL = process.env.SARVAM_MODEL || "bulbul:v3",
  SSPK = process.env.SARVAM_SPEAKER || "shubh", SPACE = parseFloat(process.env.SARVAM_PACE || "0.9");
async function sarvam(b, dst) {
  const h = createHash("sha1").update(SMODEL + SSPK + SPACE + b.say).digest("hex").slice(0, 12), cache = `/tmp/bb_sv_${h}.wav`;
  if (!existsSync(cache)) {
    const r = await fetch("https://api.sarvam.ai/text-to-speech", {
      method: "POST", headers: {"api-subscription-key": SKEY, "Content-Type": "application/json"},
      body: JSON.stringify({text: b.say, target_language_code: "en-IN", speaker: SSPK, model: SMODEL,
        pace: SPACE, speech_sample_rate: 24000})});
    if (!r.ok) throw new Error(`Sarvam ${r.status}: ${await r.text()}`);
    const j = await r.json();
    writeFileSync(cache, Buffer.from(j.audios[0], "base64"));
  }
  execFileSync("cp", [cache, dst]);
}
const out = [];
for (const b of beats) {
  if (SKEY) {
    const src = `/tmp/bb_${b.id}_sv.wav`, wav = `public/vo/${b.id}.wav`;
    await sarvam(b, src);
    execFileSync("ffmpeg", ["-y", "-v", "error", "-i", src, "-ar", "48000", "-ac", "1", "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,loudnorm=I=-16:TP=-1.5", wav]);
    b._done = true;
  } else if (KEY) {
    const mp3 = `/tmp/bb_${b.id}.mp3`, wav = `public/vo/${b.id}.wav`;
    await eleven(b, mp3);
    execFileSync("ffmpeg", ["-y", "-v", "error", "-i", mp3, "-ar", "48000", "-ac", "1", "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,atempo=" + (process.env.ATEMPO || "1.12") + ",loudnorm=I=-16:TP=-1.5", wav]);
    b._done = true;
  }
  if (!b._done) {
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
  }
  const wav = `public/vo/${b.id}.wav`;
  const sec = parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav]).toString());
  out.push({id: b.id, section: b.section, chip: b.chip, cap: b.cap ?? b.say, audio: `vo/${b.id}.wav`,
    audioFrames: Math.ceil(sec * FPS), frames: Math.ceil((sec + PAD[b.section] + (b.hold ?? 0)) * FPS), shots: []});
  console.log(b.id, sec.toFixed(2) + "s");
}
writeFileSync("src/timeline.json", JSON.stringify(out, null, 1));
const tot = (s) => out.filter((b) => b.section === s).reduce((a, b) => a + b.frames, 0) / FPS;
console.log("hook", tot("hook"), "solution", tot("solution"), "demo", tot("demo"), "impact", tot("impact"), "end", tot("end"),
  "total", out.reduce((a, b) => a + b.frames, 0) / FPS);
