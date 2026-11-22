import React from "react";
import {AbsoluteFill, Img, interpolate, Sequence, staticFile, useCurrentFrame} from "remotion";
import {C, fontFamily} from "../theme";
import {ease} from "../ui";
import {sectionRange, Shot} from "../timeline";

// Screenshot frame on the canvas
const FX = 200, FY = 62, FW = 1520, FH = 855, K = FW / 1920;
const XFADE = 8, MOVE = 20;
const clamp = {extrapolateLeft: "clamp", extrapolateRight: "clamp"} as const;

type Seg = {from: number; dur: number; img: string; shot: Shot; typingIdx?: number};

function schedule() {
  const {start, beats} = sectionRange("demo");
  const segs: Seg[] = [];
  const chips: {from: number; dur: number; label: string}[] = [];
  for (const b of beats) {
    const local = b.start - start;
    chips.push({from: local, dur: b.frames, label: b.chip ?? ""});
    const wsum = b.shots.reduce((a, s) => a + s.w, 0);
    let t = local;
    b.shots.forEach((s, i) => {
      const dur = i === b.shots.length - 1 ? local + b.frames - t : Math.round((s.w / wsum) * b.frames);
      const fr = s.frames;
      if (s.typing && fr) {
        const per = Math.max(2, Math.floor(dur / fr.length));
        fr.forEach((img, k) => segs.push({from: t + k * per, dur: k === fr.length - 1 ? dur - k * per : per, img, shot: {...s, click: k === 0 ? s.click : undefined}, typingIdx: k}));
      } else segs.push({from: t, dur, img: s.file!, shot: s});
      t += dur;
    });
  }
  return {segs, chips};
}
const {segs, chips} = schedule();
const clicks = segs.filter((s) => s.shot.click).map((s) => ({t: s.from, x: FX + s.shot.click!.x * K, y: FY + s.shot.click!.y * K, typing: s.typingIdx !== undefined}));

const Cursor: React.FC = () => {
  const f = useCurrentFrame();
  let x = FX + FW * 0.62, y = FY + FH * 0.55;
  let ripple = -1;
  let px = x, py = y;
  for (const c of clicks) {
    if (f >= c.t - MOVE) {
      const p = interpolate(f, [c.t - MOVE, c.t - 2], [0, 1], {...clamp, easing: ease});
      x = px + (c.x - px) * p; y = py + (c.y - py) * p;
      if (f >= c.t - 2 && f < c.t + 16) ripple = f - (c.t - 2);
    }
    if (f >= c.t) { px = c.x; py = c.y; }
  }
  return (
    <>
      {ripple >= 0 && (
        <div style={{position: "absolute", left: x - 34, top: y - 34, width: 68, height: 68, borderRadius: "50%", border: `4px solid ${C.live}`,
          opacity: interpolate(ripple, [0, 18], [0.9, 0]), scale: interpolate(ripple, [0, 18], [0.3, 1.3])}} />
      )}
      <svg width="40" height="40" viewBox="0 0 24 24" style={{position: "absolute", left: x - 6, top: y - 3, filter: "drop-shadow(0 2px 3px rgba(0,0,0,.45))"}}>
        <path d="M4 2 L4 19 L8.5 14.8 L11.4 21.4 L14.2 20.2 L11.3 13.7 L17.5 13.7 Z" fill="#111" stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
    </>
  );
};

const ShotImg: React.FC<{seg: Seg}> = ({seg}) => {
  const f = useCurrentFrame(); // local to the Sequence
  const fade = seg.typingIdx && seg.typingIdx > 0 ? 1 : interpolate(f, [0, XFADE], [0, 1], clamp);
  let style: React.CSSProperties = {width: FW, height: FH};
  if (seg.shot.focus) {
    const [bx, by, bw, bh] = seg.shot.focus;
    const S = Math.min(1.75, (0.94 * 1080) / bh, (0.94 * 1920) / bw);
    const T = (c: number, len: number) => Math.min(0, Math.max(len - len * S, len / 2 - c * S));
    const p = interpolate(f, [18, 60], [0, 1], {...clamp, easing: ease});
    const s = 1 + (S - 1) * p;
    const tx = T(bx + bw / 2, 1920) * p * K, ty = T(by + bh / 2, 1080) * p * K;
    style = {...style, transformOrigin: "0 0", scale: String(s), translate: `${tx}px ${ty}px`};
  }
  return (
    <div style={{position: "absolute", inset: 0, opacity: fade, overflow: "hidden", borderRadius: 18}}>
      <Img src={staticFile(seg.img)} style={style} />
    </div>
  );
};

export const Demo: React.FC = () => {
  const f = useCurrentFrame();
  const chip = chips.find((c) => f >= c.from && f < c.from + c.dur);
  const zooming = segs.some((s) => s.shot.focus && f >= s.from && f < s.from + s.dur);
  return (
    <AbsoluteFill style={{background: C.night, fontFamily}}>
      <div style={{position: "absolute", left: FX, top: 14, display: "flex", gap: 14, alignItems: "center"}}>
        <div style={{fontSize: 24, fontWeight: 800, color: "#fff", background: C.live, borderRadius: 8, padding: "5px 12px", letterSpacing: 1}}>PROTOTYPE DEMO</div>
        <div style={{fontSize: 28, fontWeight: 700, color: "#ddd"}}>{chip?.label}</div>
        <div style={{fontSize: 24, color: "#888", marginLeft: 8}}>live app · localhost · real October 2026 data</div>
      </div>
      <div style={{position: "absolute", left: FX, top: FY, width: FW, height: FH, borderRadius: 18, overflow: "hidden",
        boxShadow: "0 30px 80px rgba(0,0,0,.55)", background: "#222"}}>
        {segs.map((s, i) => (
          <Sequence key={i} from={s.from} durationInFrames={s.dur + (i < segs.length - 1 ? XFADE : 0)} layout="absolute-fill">
            <ShotImg seg={s} />
          </Sequence>
        ))}
      </div>
      {!zooming && <Cursor />}
    </AbsoluteFill>
  );
};
