import React from "react";
import {AbsoluteFill, interpolate, Sequence, staticFile, useCurrentFrame} from "remotion";
import {Audio} from "@remotion/media";
import {Hook} from "./scenes/Hook";
import {Solution} from "./scenes/Solution";
import {Demo} from "./scenes/Demo";
import {End, Impact} from "./scenes/Impact";
import {placed, sectionRange} from "./timeline";
import {Caption} from "./ui";

const FadeIn: React.FC<{children: React.ReactNode}> = ({children}) => {
  const f = useCurrentFrame();
  return <AbsoluteFill style={{opacity: interpolate(f, [0, 10], [0, 1], {extrapolateRight: "clamp"})}}>{children}</AbsoluteFill>;
};

const SCENES = {hook: Hook, solution: Solution, demo: Demo, impact: Impact, end: End} as const;

export const BharosaVideo: React.FC = () => (
  <AbsoluteFill style={{background: "#000"}}>
    {(Object.keys(SCENES) as (keyof typeof SCENES)[]).map((s) => {
      const r = sectionRange(s);
      const Scene = SCENES[s];
      return (
        <Sequence key={s} name={s} from={r.start} durationInFrames={r.end - r.start} layout="absolute-fill">
          <FadeIn><Scene /></FadeIn>
        </Sequence>
      );
    })}
    {placed.map((b) => (
      <Sequence key={b.id} name={`vo ${b.id}`} from={b.start} durationInFrames={b.frames} layout="absolute-fill">
        <Audio src={staticFile(b.audio)} />
        <Caption text={b.cap} frames={b.audioFrames} dark={b.section !== "solution" && b.section !== "impact"} bottom={b.section === "demo" ? 26 : 40} />
      </Sequence>
    ))}
  </AbsoluteFill>
);
