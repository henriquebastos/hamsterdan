import {VIDEO} from "../src/config";
import {readingSeconds} from "../src/timing";
import {
  changedRegion,
  fitsFrame,
  framingWindow,
  isNearIdentical,
  walkWindow,
  type ChangedRegion,
  type Raster,
  type Region,
  type Size,
} from "./region";

export type TransitionState = Readonly<{
  id: string;
  file: string;
  dimensions: Size;
  // The bounding box of the checkpoint's target element in document
  // coordinates, recorded at capture time. A watched page state has none.
  anchor: Region | null;
  // Caption for the transition that arrives at this state; it comes from the
  // manifest, never from anything the renderer invents about the pixels.
  caption: string;
}>;

export type TransitionFraming = "changed-region" | "anchor" | "page-walk";

export type Transition = Readonly<{
  index: number;
  fromId: string;
  toId: string;
  caption: string;
  framing: TransitionFraming;
  canvas: Size;
  window: Region;
  changedPixels: number;
  leadSeconds: number;
  crossfadeSeconds: number;
  holdSeconds: number;
}>;

// Pacing comes from the studio's cadence contract, not from new constants:
// the arriving state is held for its reading time, the departing state is held
// for one guide lead, and the crossfade takes one transition margin.
// Every hold lands on a whole frame so the encoded duration is the planned
// duration, not the planned duration plus rounding.
export const toWholeFrames = (seconds: number): number => Math.round(seconds * VIDEO.fps) / VIDEO.fps;

export const LEAD_SECONDS = toWholeFrames(VIDEO.reading.guideLeadSeconds);
export const CROSSFADE_SECONDS = toWholeFrames(VIDEO.reading.transitionMarginSeconds);

export const transitionSeconds = (transition: Transition): number =>
  transition.leadSeconds + transition.crossfadeSeconds + transition.holdSeconds;

export const planSeconds = (plan: readonly Transition[]): number =>
  plan.reduce((total, transition) => total + transitionSeconds(transition), 0);

const canvasOf = (before: TransitionState, after: TransitionState): Size => {
  if (before.dimensions.width !== after.dimensions.width) {
    throw new Error(`states ${before.id} and ${after.id} differ in width`);
  }
  return {
    width: before.dimensions.width,
    height: Math.max(before.dimensions.height, after.dimensions.height),
  };
};

export const planTransition = (
  index: number,
  count: number,
  before: TransitionState,
  after: TransitionState,
  beforeRaster: Raster,
  afterRaster: Raster,
  frame: Size,
): Transition => {
  const canvas = canvasOf(before, after);
  const changed = changedRegion(beforeRaster, afterRaster);
  const anchor = after.anchor ?? before.anchor;
  // Show the change when the frame can hold all of it. Otherwise the change is
  // either absent (a static page) or spread across the whole page, and the
  // checkpoint's own anchor names the subject better than any crop of the diff.
  const showsChange = !isNearIdentical(changed, canvas) && fitsFrame((changed as ChangedRegion).region, frame);
  const framing: TransitionFraming = showsChange ? "changed-region" : anchor ? "anchor" : "page-walk";
  const window =
    framing === "changed-region"
      ? framingWindow((changed as ChangedRegion).region, frame, canvas)
      : framing === "anchor"
        ? framingWindow(anchor as Region, frame, canvas)
        : walkWindow(index + 1, count, frame, canvas);
  return {
    index,
    fromId: before.id,
    toId: after.id,
    caption: after.caption,
    framing,
    canvas,
    window,
    changedPixels: changed?.changedPixels ?? 0,
    leadSeconds: LEAD_SECONDS,
    crossfadeSeconds: CROSSFADE_SECONDS,
    holdSeconds: toWholeFrames(readingSeconds(after.caption)),
  };
};

export const planTransitions = (
  states: readonly TransitionState[],
  rasters: readonly Raster[],
  frame: Size,
): readonly Transition[] => {
  if (states.length < 2 || states.length !== rasters.length) {
    throw new Error("a transition render needs at least two captured states");
  }
  return states
    .slice(1)
    .map((after, index) => planTransition(index, states.length, states[index], after, rasters[index], rasters[index + 1], frame));
};
