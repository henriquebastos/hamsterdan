import {VIDEO} from "./config";

export type ReadingOptions = {
  wordsPerSecond?: number;
  minimumHoldSeconds?: number;
  transitionMarginSeconds?: number;
};

export const secondsToFrames = (seconds: number): number =>
  Math.round(seconds * VIDEO.fps);

export const wordCount = (text: string): number =>
  text.trim().split(/\s+/u).filter(Boolean).length;

export const readingSeconds = (
  text: string,
  options: ReadingOptions = {},
): number => {
  const wordsPerSecond = options.wordsPerSecond ?? VIDEO.reading.wordsPerSecond;
  const minimumHoldSeconds =
    options.minimumHoldSeconds ?? VIDEO.reading.minimumHoldSeconds;

  return Math.max(minimumHoldSeconds, wordCount(text) / wordsPerSecond);
};

export const readingFrames = (
  text: string,
  options: ReadingOptions = {},
): number => secondsToFrames(readingSeconds(text, options));

export const nextBeatFrame = (
  currentFrame: number,
  mainText: string,
  options: ReadingOptions = {},
): number =>
  currentFrame +
  readingFrames(mainText, options) +
  secondsToFrames(options.transitionMarginSeconds ?? 0.8);

export const eventAfterGuideFrame = (guideFrame: number): number =>
  guideFrame + secondsToFrames(VIDEO.reading.guideLeadSeconds);
