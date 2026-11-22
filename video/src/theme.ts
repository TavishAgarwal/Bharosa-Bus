import {loadFont} from "@remotion/google-fonts/Inter";
import {loadFont as loadDeva} from "@remotion/google-fonts/NotoSansDevanagari";

export const {fontFamily} = loadFont("normal", {weights: ["400", "600", "700", "800"], subsets: ["latin"]});
export const {fontFamily: devaFamily} = loadDeva("normal", {weights: ["600", "700"], subsets: ["devanagari"]});

export const C = {
  seats: "#1a7f37",
  standing: "#b7791f",
  crowded: "#c62828",
  unknown: "#9e9e9e",
  ink: "#161616",
  mute: "#6b6b6b",
  line: "#e8e8e8",
  paper: "#f6f6f4",
  night: "#101010",
  live: "#1f6feb",
};
export const FPS = 30;
export const INTRO = 75; // title card before the first line of narration
