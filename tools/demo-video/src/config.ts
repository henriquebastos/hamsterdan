export const VIDEO = {
  width: 1920,
  height: 1080,
  fps: 30,
  targetDurationSeconds: 179,
  acts: {
    opening: 14,
    review: 30,
    conversation: 32,
    repair: 33,
    recovery: 38,
    approval: 32,
  },
  reading: {
    wordsPerSecond: 3.8,
    minimumHoldSeconds: 2.5,
    guideLeadSeconds: 1.2,
    transitionMarginSeconds: 0.8,
  },
} as const;

export type VideoConfig = typeof VIDEO;

export const COLORS = {
  background: "#070b12",
  surface: "#0d1117",
  surfaceRaised: "#161b22",
  border: "#30363d",
  text: "#f0f6fc",
  muted: "#8b949e",
  dan: "#f0883e",
  henrique: "#58a6ff",
  cris: "#db61a2",
  success: "#3fb950",
  system: "#a371f7",
  warning: "#d29922",
  danger: "#f85149",
} as const;
