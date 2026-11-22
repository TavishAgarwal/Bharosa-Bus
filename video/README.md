# Demo video (Remotion)

About 3:20 at 1920×1080: opening hook, solution overview, a demo of the live app, then impact and next steps.
The demo part is one continuous, uncut recording of the running app.

```bash
# 1. start the live app (from the repo root): make serve, or python -m bharosa.serve 8010
# 2. use Node 22 (Remotion's CLI hangs on Node 26)
nvm use 22
npm i
node scripts/voice.mjs                           # voiceover -> public/vo + src/timeline.json (see engines below)
node scripts/record.mjs http://127.0.0.1:8010    # one-take recording of the live app -> public/rec/demo.mp4 (needs Google Chrome)
npx remotion studio                              # preview
npx remotion render BharosaBusDemo out/bharosa-bus-demo.mp4 --codec=h264 --crf=18
```

- Narration and captions: `scripts/beats.mjs` (edit text there, then rerun `voice.mjs`). Scene lengths follow the voice.
- Scenes: `src/scenes/` (Hook, Solution, Demo, Impact + End card).
- The prototype demo is ONE continuous recording of the live app: no cuts, no stills. `record.mjs` drives headless Chrome with real
  mouse and keyboard input (cursor drawn in the page), timed to the narration in `src/timeline.json`; it prints planned vs actual
  time for each beat. Rerun it whenever the narration changes. The only effect added in Remotion is a camera zoom on two details.

### Narration engines

The shipped video uses Sarvam AI (`bulbul:v3`, Indian English, speaker "shubh", pace 0.9):

    SARVAM_API_KEY=... node scripts/voice.mjs          # optional: SARVAM_SPEAKER=aditya, SARVAM_PACE=1.0

ElevenLabs also works (default voice "Daniel", sped up 12% with ffmpeg).
Set keys in your shell, never in a file in this repo:

    ELEVENLABS_API_KEY=... node scripts/voice.mjs      # optional: ELEVEN_VOICE=<voice id>, ATEMPO=1.0

Takes are cached in /tmp by voice and text, so re-running only spends characters on changed lines.
Sarvam wins if both keys are set. Without either key, the script falls back to macOS `say`.
