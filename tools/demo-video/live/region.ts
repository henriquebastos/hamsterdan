export type Region = Readonly<{x: number; y: number; width: number; height: number}>;

export type Size = Readonly<{width: number; height: number}>;

export type Raster = Readonly<{width: number; height: number; pixels: Uint8Array}>;

export type ChangedRegion = Readonly<{region: Region; changedPixels: number}>;

// A montage of full-page stills is unreadable because a 1280x4653 page fitted
// into a 1280x720 frame is a sliver. The transition renderer instead shows the
// pixels that actually changed between two consecutive stills, at 1:1.
export const changedRegion = (before: Raster, after: Raster): ChangedRegion | null => {
  if (before.width !== after.width) {
    throw new Error("changed-region detection requires two stills of the same width");
  }
  const width = before.width;
  const height = Math.max(before.height, after.height);
  let minX = width;
  let maxX = -1;
  let minY = height;
  let maxY = -1;
  let changedPixels = 0;

  for (let y = 0; y < height; y += 1) {
    // A row that exists in only one still is entirely new content.
    if (y >= before.height || y >= after.height) {
      minX = 0;
      maxX = width - 1;
      if (y < minY) minY = y;
      maxY = y;
      changedPixels += width;
      continue;
    }
    const beforeRow = y * width * 4;
    const afterRow = y * width * 4;
    let rowChanged = false;
    for (let x = 0; x < width; x += 1) {
      const b = beforeRow + x * 4;
      const a = afterRow + x * 4;
      if (
        before.pixels[b] !== after.pixels[a] ||
        before.pixels[b + 1] !== after.pixels[a + 1] ||
        before.pixels[b + 2] !== after.pixels[a + 2] ||
        before.pixels[b + 3] !== after.pixels[a + 3]
      ) {
        rowChanged = true;
        changedPixels += 1;
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
      }
    }
    if (rowChanged) {
      if (y < minY) minY = y;
      maxY = y;
    }
  }

  if (changedPixels === 0) return null;
  return {
    region: {x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1},
    changedPixels,
  };
};

// Anti-aliasing and a moving :target highlight leave a handful of stray pixels
// even when a closed pull request has not changed. Below this share of the
// canvas the pair counts as static and the renderer frames the checkpoint
// anchor instead of a meaningless diff.
export const NEAR_IDENTICAL_CHANGED_RATIO = 0.001;

export const isNearIdentical = (changed: ChangedRegion | null, canvas: Size): boolean =>
  changed === null || changed.changedPixels / (canvas.width * canvas.height) < NEAR_IDENTICAL_CHANGED_RATIO;

// A change the frame cannot hold whole is not something the frame can honestly
// claim to show. On a closed pull request the relative timestamps redraw from
// the header to the footer, so the "changed region" is nearly the entire page;
// framing its first rows would put the page header on screen under a caption
// about a comment thousands of pixels below.
export const fitsFrame = (region: Region, frame: Size): boolean =>
  region.width <= frame.width && region.height <= frame.height;

const clamp = (value: number, low: number, high: number): number => Math.min(Math.max(value, low), high);

// The window is exactly the frame size so the crop is 1:1 — never scaled — and
// it always lies inside the canvas so both stills of a transition can supply it.
export const framingWindow = (region: Region, frame: Size, canvas: Size): Region => {
  const width = Math.min(frame.width, canvas.width);
  const height = Math.min(frame.height, canvas.height);
  const centeredX = Math.round(region.x + region.width / 2 - width / 2);
  // A region taller than the frame cannot be shown whole, so the window starts
  // at its first changed row: reading order, not an arbitrary midpoint.
  const y = region.height > height ? region.y : Math.round(region.y + region.height / 2 - height / 2);
  return {
    x: clamp(centeredX, 0, canvas.width - width),
    y: clamp(y, 0, canvas.height - height),
    width,
    height,
  };
};

// Last resort for a static journey whose capture recorded no anchor box: walk
// the camera down the page, one evenly spaced window per state.
export const walkWindow = (index: number, count: number, frame: Size, canvas: Size): Region => {
  const width = Math.min(frame.width, canvas.width);
  const height = Math.min(frame.height, canvas.height);
  const travel = canvas.height - height;
  const steps = Math.max(1, count - 1);
  return {x: 0, y: clamp(Math.round((index * travel) / steps), 0, travel), width, height};
};
