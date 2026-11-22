import raw from "./timeline.json";
import {INTRO} from "./theme";

export type Shot = {file?: string; frames?: string[]; typing?: boolean; click?: {x: number; y: number}; focus?: number[]; w: number};
export type Beat = {id: string; section: "hook" | "solution" | "demo" | "impact" | "end"; chip?: string; cap: string; audio: string;
  audioFrames: number; frames: number; shots: Shot[]};
export type Placed = Beat & {start: number};

export const beats = raw as Beat[];
// beat start frames on the main timeline (the hook gets the title card in front)
export const placed: Placed[] = (() => {
  let t = INTRO;
  return beats.map((b) => { const p = {...b, start: t}; t += b.frames; return p; });
})();
export const TOTAL = placed.reduce((a, b) => Math.max(a, b.start + b.frames), 0);
export const sectionRange = (s: Beat["section"]) => {
  const xs = placed.filter((b) => b.section === s);
  const start = s === "hook" ? 0 : xs[0].start;
  return {start, end: xs[xs.length - 1].start + xs[xs.length - 1].frames, beats: xs};
};
