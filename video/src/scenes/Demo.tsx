import React from "react";
import {AbsoluteFill, interpolate, OffthreadVideo, staticFile, useCurrentFrame} from "remotion";
import {C, fontFamily, FPS} from "../theme";
import {ease} from "../ui";
import {sectionRange} from "../timeline";
import zoomRaw from "../zoom.json";

// One continuous recording of the live app (scripts/record.mjs): no cuts and no stills. The only effect is a
// camera zoom (a crop of the same frames) on two details, so the take itself stays visibly unbroken.
const FX = 200, FY = 62, FW = 1520, FH = 855, K = FW / 1920;
const clamp = {extrapolateLeft: "clamp", extrapolateRight: "clamp"} as const;
type Zoom = {from: number; to: number; box: number[]};
const zooms = zoomRaw as Zoom[];

const {beats, start} = sectionRange("demo");
const chips = beats.map((b) => ({from: b.start - start, dur: b.frames, label: b.chip ?? ""}));

function camera(f: number) {
  for (const z of zooms) {
    const a = z.from * FPS, b = z.to * FPS;
    if (f < a || f > b) continue;
    const [bx, by, bw, bh] = z.box;
    const S = Math.min(1.7, (0.92 * 1080) / bh, (0.92 * 1920) / bw);
    const T = (c: number, len: number) => Math.min(0, Math.max(len - len * S, len / 2 - c * S));
    const p = Math.min(interpolate(f, [a, a + 24], [0, 1], {...clamp, easing: ease}), interpolate(f, [b - 18, b], [1, 0], {...clamp, easing: ease}));
    return {s: 1 + (S - 1) * p, tx: T(bx + bw / 2, 1920) * p * K, ty: T(by + bh / 2, 1080) * p * K};
  }
  return {s: 1, tx: 0, ty: 0};
}

export const Demo: React.FC = () => {
  const f = useCurrentFrame();
  const chip = chips.find((c) => f >= c.from && f < c.from + c.dur);
  const {s, tx, ty} = camera(f);
  const sec = Math.floor(f / FPS);
  const clock = `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
  return (
    <AbsoluteFill style={{background: C.night, fontFamily}}>
      <div style={{position: "absolute", left: FX, right: 1920 - FX - FW, top: 14, display: "flex", gap: 14, alignItems: "center"}}>
        <div style={{fontSize: 24, fontWeight: 800, color: "#fff", background: C.live, borderRadius: 8, padding: "5px 12px", letterSpacing: 1}}>PROTOTYPE DEMO</div>
        <div style={{fontSize: 28, fontWeight: 700, color: "#ddd"}}>{chip?.label}</div>
        <div style={{fontSize: 22, color: "#888", marginLeft: 8}}>live app · real October 2026 data</div>
        <div style={{marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, fontSize: 22, color: "#ddd", fontVariantNumeric: "tabular-nums"}}>
          <span style={{width: 14, height: 14, borderRadius: 7, background: "#e5484d", opacity: f % 30 < 18 ? 1 : 0.35}} />
          ONE TAKE · NO CUTS · {clock}
        </div>
      </div>
      <div style={{position: "absolute", left: FX, top: FY, width: FW, height: FH, borderRadius: 18, overflow: "hidden",
        boxShadow: "0 30px 80px rgba(0,0,0,.55)", background: "#222"}}>
        <OffthreadVideo src={staticFile("rec/demo.mp4")} muted
          style={{width: FW, height: FH, transformOrigin: "0 0", scale: String(s), translate: `${tx}px ${ty}px`}} />
      </div>
    </AbsoluteFill>
  );
};
