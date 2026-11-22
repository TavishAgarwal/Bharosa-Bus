import React from "react";
import {Easing, interpolate, useCurrentFrame} from "remotion";
import {C, fontFamily} from "./theme";

const clamp = {extrapolateLeft: "clamp", extrapolateRight: "clamp"} as const;
export const ease = Easing.bezier(0.16, 1, 0.3, 1);
// 0 -> 1 over `len` frames starting at `at`
export const rise = (f: number, at: number, len = 18) => interpolate(f, [at, at + len], [0, 1], {...clamp, easing: ease});

export const FadeUp: React.FC<{at: number; children: React.ReactNode; style?: React.CSSProperties; dist?: number}> = ({at, children, style, dist = 30}) => {
  const f = useCurrentFrame();
  const p = rise(f, at);
  return <div style={{opacity: p, translate: `0px ${(1 - p) * dist}px`, ...style}}>{children}</div>;
};

export const Pill: React.FC<{color: string; label: string; size?: number; style?: React.CSSProperties}> = ({color, label, size = 34, style}) => (
  <div style={{display: "inline-flex", alignItems: "center", gap: size * 0.35, padding: `${size * 0.3}px ${size * 0.6}px`, borderRadius: 999,
    background: color, color: "#fff", fontWeight: 800, fontSize: size, letterSpacing: 0.5, fontFamily, ...style}}>{label}</div>
);

export const Logo: React.FC<{size?: number; dark?: boolean}> = ({size = 64, dark}) => (
  <div style={{display: "flex", alignItems: "center", gap: size * 0.3, fontFamily}}>
    <div style={{width: size, height: size, borderRadius: size * 0.27, background: dark ? "#fff" : C.ink, color: dark ? C.ink : "#fff",
      display: "grid", placeItems: "center", fontWeight: 800, fontSize: size * 0.42}}>BB</div>
    <div style={{fontWeight: 800, fontSize: size * 0.72, color: dark ? "#fff" : C.ink, letterSpacing: -0.5}}>Bharosa Bus</div>
  </div>
);

// A row of coloured stretches that fills in from left to right.
export const StretchBar: React.FC<{levels: string[]; at: number; height?: number; width?: number; per?: number}> = ({levels, at, height = 26, width = 900, per = 2}) => {
  const f = useCurrentFrame();
  return (
    <div style={{display: "flex", gap: 4, width, height}}>
      {levels.map((l, i) => {
        const p = rise(f, at + i * per, 10);
        return <div key={i} style={{flex: 1, borderRadius: 5, background: (C as Record<string, string>)[l] ?? C.unknown, opacity: 0.15 + 0.85 * p, scale: `1 ${0.4 + 0.6 * p}`}} />;
      })}
    </div>
  );
};

// Caption strip: splits the beat text into sentences and shows each for a share of the beat's audio.
export const Caption: React.FC<{text: string; frames: number; dark?: boolean; bottom?: number}> = ({text, frames, dark = true, bottom = 34}) => {
  const f = useCurrentFrame();
  if (!text) return null;
  // split after . ! ? or : only when the next word starts a new sentence (capital, digit or opening quote)
  const parts = text.split(/(?<=[.!?:][\u201d"]?)\s+(?=[A-Z0-9\u201c"])/).map((s) => s.trim()).filter(Boolean);
  // merge tiny fragments into the previous sentence
  const chunks: string[] = [];
  for (const p of parts) (chunks.length && p.length < 28 ? (chunks[chunks.length - 1] += " " + p) : chunks.push(p));
  const total = chunks.reduce((a, c) => a + c.length, 0);
  let acc = 0, idx = 0;
  for (let i = 0; i < chunks.length; i++) { const end = acc + (chunks[i].length / total) * frames; if (f < end) { idx = i; break; } acc = end; idx = i; }
  return (
    <div style={{position: "absolute", left: 0, right: 0, bottom, display: "flex", justifyContent: "center", pointerEvents: "none"}}>
      <div style={{maxWidth: 1560, textAlign: "center", fontFamily, fontSize: 36, lineHeight: 1.3, fontWeight: 600,
        color: dark ? "#fff" : C.ink, background: dark ? "rgba(0,0,0,.62)" : "rgba(255,255,255,.85)", padding: "10px 26px", borderRadius: 14}}>
        {chunks[idx]}
      </div>
    </div>
  );
};
