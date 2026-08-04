import React from "react";
import {Composition} from "remotion";
import {FullMotion} from "./scenarios/pr47-hero";
import {VIDEO} from "./config";

export const Root: React.FC = () => (
  <Composition
    id="PR47Hero"
    component={FullMotion}
    durationInFrames={VIDEO.targetDurationSeconds * VIDEO.fps}
    fps={VIDEO.fps}
    width={VIDEO.width}
    height={VIDEO.height}
  />
);
