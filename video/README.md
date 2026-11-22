# Demo video (Remotion)

About 2:40 at 1920×1080: opening hook, solution overview, a demo of the live app, then impact and next steps.
The demo part uses real screenshots of the running app, not mock-ups.

```bash
# 1. start the live app (from the repo root): make serve, or python -m bharosa.serve 8010
# 2. use Node 22 (Remotion's CLI hangs on Node 26)
nvm use 22
npm i
node scripts/capture.mjs http://127.0.0.1:8010   # screenshots -> public/shots (needs Google Chrome)
node scripts/voice.mjs                           # macOS `say` voiceover -> public/vo + src/timeline.json
npx remotion studio                              # preview
npx remotion render BharosaBusDemo out/bharosa-bus-demo.mp4 --codec=h264 --crf=18
```

- Narration and captions: `scripts/beats.mjs` (edit text there, then rerun `voice.mjs`). Scene lengths follow the voice.
- Scenes: `src/scenes/` (Hook, Solution, Demo, Impact + End card).
- Clicks in the demo come from where `capture.mjs` really clicked, so the cursor lines up with the controls.
