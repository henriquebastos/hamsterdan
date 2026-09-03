import {describe, expect, test} from "bun:test";
import {VIDEO} from "../src/config";
import {readingSeconds} from "../src/timing";
import type {Raster, Region} from "./region";
import {
  CROSSFADE_SECONDS,
  LEAD_SECONDS,
  planSeconds,
  planTransitions,
  toWholeFrames,
  transitionSeconds,
  type TransitionState,
} from "./transition";

const FRAME = {width: 128, height: 64};

const raster = (width: number, height: number, paint?: Region): Raster => {
  const pixels = new Uint8Array(width * height * 4).fill(255);
  if (paint) {
    for (let y = paint.y; y < paint.y + paint.height; y += 1) {
      for (let x = paint.x; x < paint.x + paint.width; x += 1) {
        pixels[(y * width + x) * 4] = 0;
      }
    }
  }
  return {width, height, pixels};
};

const state = (id: string, caption: string, height: number, anchor: Region | null = null): TransitionState => ({
  id,
  file: `checkpoints/${id}.png`,
  dimensions: {width: 128, height},
  anchor,
  caption,
});

describe("transition plan", () => {
  test("produces one transition per consecutive pair of captured states", () => {
    const states = [state("state-001", "one", 400), state("state-002", "two", 400), state("state-003", "three", 400)];
    const rasters = [
      raster(128, 400),
      raster(128, 400, {x: 10, y: 100, width: 20, height: 10}),
      raster(128, 400, {x: 10, y: 300, width: 20, height: 10}),
    ];
    const plan = planTransitions(states, rasters, FRAME);
    expect(plan.map(({fromId, toId}) => `${fromId}->${toId}`)).toEqual([
      "state-001->state-002",
      "state-002->state-003",
    ]);
  });

  test("frames the changed pixels when a page state actually changed", () => {
    const states = [state("state-001", "one", 400), state("state-002", "two", 400)];
    const rasters = [raster(128, 400), raster(128, 400, {x: 10, y: 200, width: 40, height: 12})];
    const [transition] = planTransitions(states, rasters, FRAME);
    expect(transition.framing).toBe("changed-region");
    expect(transition.window.height).toBe(FRAME.height);
    // The changed rows 200..211 must lie inside the window the video shows.
    expect(transition.window.y).toBeLessThanOrEqual(200);
    expect(transition.window.y + transition.window.height).toBeGreaterThanOrEqual(212);
  });

  test("frames the checkpoint anchor when a static journey has no meaningful diff", () => {
    const anchor = {x: 0, y: 300, width: 128, height: 40};
    const states = [state("findings", "one", 400), state("readiness", "two", 400, anchor)];
    const identical = [raster(128, 400), raster(128, 400)];
    const [transition] = planTransitions(states, identical, FRAME);
    expect(transition.framing).toBe("anchor");
    expect(transition.changedPixels).toBe(0);
    expect(transition.window.y).toBeLessThanOrEqual(anchor.y);
    expect(transition.window.y + transition.window.height).toBeGreaterThanOrEqual(anchor.y + anchor.height);
  });

  test("falls back to the anchor when the change is spread across the whole page", () => {
    // A closed pull request redraws its relative timestamps from header to
    // footer, so the changed region covers nearly the whole page and no crop of
    // it can honestly be called the change.
    const anchor = {x: 0, y: 300, width: 128, height: 40};
    const states = [state("findings", "one", 400), state("readiness", "two", 400, anchor)];
    const diffuse = [raster(128, 400), raster(128, 400, {x: 0, y: 4, width: 128, height: 380})];
    const [transition] = planTransitions(states, diffuse, FRAME);
    expect(transition.framing).toBe("anchor");
    expect(transition.changedPixels).toBeGreaterThan(0);
    expect(transition.window.y).toBeLessThanOrEqual(anchor.y);
    expect(transition.window.y + transition.window.height).toBeGreaterThanOrEqual(anchor.y + anchor.height);
  });

  test("walks the page when a static journey recorded no anchor at all", () => {
    const states = [state("a", "one", 400), state("b", "two", 400), state("c", "three", 400)];
    const identical = [raster(128, 400), raster(128, 400), raster(128, 400)];
    const plan = planTransitions(states, identical, FRAME);
    expect(plan.map(({framing}) => framing)).toEqual(["page-walk", "page-walk"]);
    // A camera walk, not a repeated frame: each transition lands further down.
    expect(plan[1].window.y).toBeGreaterThan(plan[0].window.y);
  });

  test("carries the arriving state's caption straight from its metadata", () => {
    const caption = "Hamsterdan readiness advisory";
    const states = [state("a", "ignored", 400), state("b", caption, 400)];
    const [transition] = planTransitions(states, [raster(128, 400), raster(128, 400, {x: 1, y: 1, width: 60, height: 30})], FRAME);
    expect(transition.caption).toBe(caption);
  });

  test("paces each hold with the studio's reading rule, not a fresh constant", () => {
    const caption = "apply the three fixes from your review findings comment";
    const states = [state("a", "x", 400), state("b", caption, 400)];
    const [transition] = planTransitions(states, [raster(128, 400), raster(128, 400, {x: 1, y: 1, width: 60, height: 30})], FRAME);
    expect(transition.holdSeconds).toBe(toWholeFrames(readingSeconds(caption)));
    expect(transition.leadSeconds).toBe(toWholeFrames(VIDEO.reading.guideLeadSeconds));
    expect(transition.crossfadeSeconds).toBe(toWholeFrames(VIDEO.reading.transitionMarginSeconds));
  });

  test("holds a short caption for the contract's minimum reading time", () => {
    const states = [state("a", "x", 400), state("b", "ok", 400)];
    const [transition] = planTransitions(states, [raster(128, 400), raster(128, 400, {x: 1, y: 1, width: 4, height: 4})], FRAME);
    expect(transition.holdSeconds).toBe(toWholeFrames(VIDEO.reading.minimumHoldSeconds));
  });

  test("sums each segment as lead plus crossfade plus hold", () => {
    const states = [state("a", "x", 400), state("b", "one two three four", 400)];
    const plan = planTransitions(states, [raster(128, 400), raster(128, 400, {x: 1, y: 1, width: 4, height: 4})], FRAME);
    expect(transitionSeconds(plan[0])).toBe(LEAD_SECONDS + CROSSFADE_SECONDS + plan[0].holdSeconds);
    expect(planSeconds(plan)).toBe(transitionSeconds(plan[0]));
  });

  test("every planned duration lands on a whole frame", () => {
    const states = [state("a", "x", 400), state("b", "a caption with several words in it", 400)];
    const plan = planTransitions(states, [raster(128, 400), raster(128, 400, {x: 1, y: 1, width: 4, height: 4})], FRAME);
    for (const seconds of [plan[0].leadSeconds, plan[0].crossfadeSeconds, plan[0].holdSeconds]) {
      expect(Number.isInteger(seconds * VIDEO.fps)).toBeTrue();
    }
  });

  test("refuses to plan a journey with fewer than two states", () => {
    expect(() => planTransitions([state("a", "x", 400)], [raster(128, 400)], FRAME)).toThrow(/at least two/);
  });

  test("refuses two states of different widths", () => {
    const states = [state("a", "x", 400), {...state("b", "y", 400), dimensions: {width: 130, height: 400}}];
    expect(() => planTransitions(states, [raster(128, 400), raster(130, 400)], FRAME)).toThrow(/differ in width/);
  });
});
