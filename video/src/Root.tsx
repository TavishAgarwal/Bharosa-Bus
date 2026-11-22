import React from "react";
import {Composition} from "remotion";
import {BharosaVideo} from "./Video";
import {TOTAL} from "./timeline";
import {FPS} from "./theme";

export const RemotionRoot: React.FC = () => (
  <Composition id="BharosaBusDemo" component={BharosaVideo} durationInFrames={TOTAL} fps={FPS} width={1920} height={1080} />
);
