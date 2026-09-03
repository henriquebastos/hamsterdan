import {describe, expect, test} from "bun:test";
import {
  changedRegion,
  framingWindow,
  isNearIdentical,
  NEAR_IDENTICAL_CHANGED_RATIO,
  walkWindow,
  type Raster,
  type Region,
} from "./region";

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

describe("changed-region detection", () => {
  test("bounds exactly the pixels that differ between two stills", () => {
    const before = raster(40, 60);
    const after = raster(40, 60, {x: 8, y: 12, width: 5, height: 7});
    const changed = changedRegion(before, after);
    expect(changed).not.toBeNull();
    expect(changed?.region).toEqual({x: 8, y: 12, width: 5, height: 7});
    expect(changed?.changedPixels).toBe(35);
  });

  test("reports nothing for two identical stills", () => {
    expect(changedRegion(raster(40, 60), raster(40, 60))).toBeNull();
  });

  test("treats rows that exist in only one still as changed content", () => {
    // A pull request that gained a comment is taller; the new rows are the
    // change even though no shared row differs.
    const changed = changedRegion(raster(40, 60), raster(40, 75));
    expect(changed?.region).toEqual({x: 0, y: 60, width: 40, height: 15});
    expect(changed?.changedPixels).toBe(40 * 15);
  });

  test("refuses two stills of different widths", () => {
    expect(() => changedRegion(raster(40, 60), raster(41, 60))).toThrow(/same width/);
  });

  test("calls a stray-pixel difference near-identical", () => {
    const canvas = {width: 1280, height: 4653};
    const strays = Math.floor(canvas.width * canvas.height * NEAR_IDENTICAL_CHANGED_RATIO) - 1;
    expect(isNearIdentical({region: {x: 0, y: 0, width: 1, height: 1}, changedPixels: strays}, canvas)).toBeTrue();
    expect(isNearIdentical(null, canvas)).toBeTrue();
    expect(
      isNearIdentical({region: {x: 0, y: 0, width: 1280, height: 400}, changedPixels: 1280 * 400}, canvas),
    ).toBeFalse();
  });
});

describe("1:1 framing window", () => {
  const frame = {width: 1280, height: 664};
  const canvas = {width: 1280, height: 4653};

  test("keeps the window exactly frame-sized so the crop is never scaled", () => {
    const window = framingWindow({x: 0, y: 2000, width: 1280, height: 120}, frame, canvas);
    expect(window.width).toBe(frame.width);
    expect(window.height).toBe(frame.height);
  });

  test("centres a region that fits inside the frame", () => {
    const window = framingWindow({x: 0, y: 2000, width: 1280, height: 100}, frame, canvas);
    expect(window.y).toBe(2000 + 50 - 332);
  });

  test("starts at the first changed row when the region is taller than the frame", () => {
    // Reading order: a 2000-row change is entered at its top, not its middle.
    expect(framingWindow({x: 0, y: 1243, width: 1280, height: 2058}, frame, canvas).y).toBe(1243);
  });

  test("never leaves the canvas", () => {
    expect(framingWindow({x: 0, y: 10, width: 1280, height: 20}, frame, canvas).y).toBe(0);
    expect(framingWindow({x: 0, y: 4650, width: 1280, height: 3}, frame, canvas).y).toBe(canvas.height - frame.height);
  });
});

describe("static page walk", () => {
  const frame = {width: 1280, height: 664};
  const canvas = {width: 1280, height: 4653};

  test("walks evenly down the page and stops at the bottom", () => {
    const travel = canvas.height - frame.height;
    expect(walkWindow(0, 3, frame, canvas).y).toBe(0);
    expect(walkWindow(1, 3, frame, canvas).y).toBe(Math.round(travel / 2));
    expect(walkWindow(2, 3, frame, canvas).y).toBe(travel);
  });

  test("stays at the top when the page is not taller than the frame", () => {
    expect(walkWindow(1, 2, frame, {width: 1280, height: 600})).toEqual({x: 0, y: 0, width: 1280, height: 600});
  });
});
