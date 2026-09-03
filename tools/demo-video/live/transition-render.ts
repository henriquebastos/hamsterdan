import {mkdir, mkdtemp, readdir, realpath, rename, rm, writeFile} from "node:fs/promises";
import {basename, join} from "node:path";
import type {Browser} from "playwright";
import {parseManifest, watchedPageUrl, type CaptureManifest} from "./manifest";
import {pngDimensions} from "./png";
import type {Raster, Size} from "./region";
import {
  canonicalDirectory,
  containedBy,
  parsePendingReport,
  readRegularFile,
  requireAbsent,
  run,
  sha256,
  type CaptureReportKind,
  type PendingReport,
  type VideoReport,
} from "./render";
import {planSeconds, planTransitions, type Transition, type TransitionState} from "./transition";

export const FRAME: Size = {width: 1280, height: 720};

// The caption strip is the only authored pixel in the frame. Everything above
// it is the captured page at 1:1.
export const CAPTION_HEIGHT = 56;

export const EVIDENCE_PANE: Size = {width: FRAME.width, height: FRAME.height - CAPTION_HEIGHT};

const escapeHtml = (value: string): string =>
  value.replace(/[&<>"']/g, (character) => `&#${character.charCodeAt(0)};`);

export const captionStripHtml = (caption: string): string =>
  `<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;padding:0;width:${FRAME.width}px;height:${CAPTION_HEIGHT}px;overflow:hidden}
  body{background:#0d1117;color:#f0f6fc;display:flex;align-items:center;
    font:500 20px/1.2 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    box-sizing:border-box;border-top:2px solid #30363d}
  div{padding:0 24px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%;box-sizing:border-box}
  </style></head><body><div>${escapeHtml(caption)}</div></body></html>`;

export const renderCaptionStrip = async (browser: Browser, caption: string): Promise<Uint8Array> => {
  const context = await browser.newContext({
    viewport: {width: FRAME.width, height: CAPTION_HEIGHT},
    deviceScaleFactor: 1,
    colorScheme: "dark",
    reducedMotion: "reduce",
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  try {
    // The caption renderer is a text compositor, not an evidence surface: it
    // must never reach the network.
    await context.route("**/*", (route) => route.abort("blockedbyclient"));
    const page = await context.newPage();
    await page.setContent(captionStripHtml(caption), {waitUntil: "load"});
    await page.evaluate(() => document.fonts.ready);
    const png = await page.screenshot({type: "png", animations: "disabled", caret: "hide"});
    const dimensions = pngDimensions(png, "caption strip");
    if (dimensions.width !== FRAME.width || dimensions.height !== CAPTION_HEIGHT) {
      throw new Error(`caption strip is ${dimensions.width}x${dimensions.height}, not ${FRAME.width}x${CAPTION_HEIGHT}`);
    }
    return png;
  } finally {
    await context.close();
  }
};

export const decodeRgba = async (path: string, dimensions: Size, label: string): Promise<Raster> => {
  const child = Bun.spawn(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgba", "-"], {
    stdout: "pipe",
    stderr: "pipe",
  });
  const [pixels, stderr, exit] = await Promise.all([
    new Response(child.stdout).arrayBuffer(),
    new Response(child.stderr).text(),
    child.exited,
  ]);
  if (exit !== 0) throw new Error(`${label} could not be decoded: ${stderr.slice(0, 500)}`);
  const expected = dimensions.width * dimensions.height * 4;
  if (pixels.byteLength !== expected) {
    throw new Error(`${label} decoded to ${pixels.byteLength} bytes, expected ${expected}`);
  }
  return {width: dimensions.width, height: dimensions.height, pixels: new Uint8Array(pixels)};
};

export type TransitionRenderReport = Readonly<{
  schema: 1;
  kind: "github-live-transition-render";
  slug: string;
  renderedAt: string;
  source: Readonly<{
    captureKind: CaptureReportKind;
    capturedAt: string;
    gitCommit: string;
    manifestSha256: string;
    reportSha256: string;
  }>;
  frame: Size;
  captionHeight: number;
  transitions: readonly Transition[];
  video: VideoReport;
}>;

const identifyCheckpointStates = (
  manifest: CaptureManifest,
  report: PendingReport<CaptureReportKind>,
): readonly TransitionState[] => {
  if (report.checkpoints.length !== manifest.checkpoints.length) {
    throw new Error("report order does not match the manifest");
  }
  return manifest.checkpoints.map((checkpoint, index) => {
    const observed = report.checkpoints[index];
    if (
      observed.id !== checkpoint.id ||
      observed.kind !== checkpoint.kind ||
      observed.target !== checkpoint.target ||
      observed.requestedUrl !== checkpoint.url ||
      observed.finalUrl !== checkpoint.url ||
      observed.file !== `checkpoints/${checkpoint.id}.png`
    ) {
      throw new Error("report checkpoint order or identity does not match the manifest");
    }
    return {
      id: observed.id,
      file: observed.file,
      dimensions: observed.dimensions,
      anchor: observed.anchor,
      // Captured page text the manifest already asserts, never new prose.
      caption: checkpoint.focusText,
    };
  });
};

const identifyWatchedStates = (
  manifest: CaptureManifest,
  report: PendingReport<CaptureReportKind>,
): readonly TransitionState[] => {
  if (!manifest.watch) {
    throw new Error("a state-sequence capture requires the manifest's watch plan");
  }
  const url = watchedPageUrl(manifest);
  if (report.checkpoints.length > manifest.watch.maxStates) {
    throw new Error("state sequence exceeds the manifest's maxStates");
  }
  return report.checkpoints.map((observed, index) => {
    const ordinal = index + 1;
    if (
      observed.kind !== "state" ||
      observed.id !== `state-${String(ordinal).padStart(3, "0")}` ||
      observed.target !== String(ordinal) ||
      observed.requestedUrl !== url ||
      observed.finalUrl !== url ||
      observed.file !== `checkpoints/${observed.id}.png`
    ) {
      throw new Error(`state sequence is not the ordered watched journey at position ${ordinal}`);
    }
    if (index > 0 && Date.parse(observed.capturedAt) < Date.parse(report.checkpoints[index - 1].capturedAt)) {
      throw new Error(`state ${observed.id} is older than the state before it`);
    }
    return {
      id: observed.id,
      file: observed.file,
      dimensions: observed.dimensions,
      anchor: observed.anchor,
      caption: `${manifest.watch!.caption} — state ${ordinal}`,
    };
  });
};

const probeVideo = async (path: string, expectedSeconds: number): Promise<Omit<VideoReport, "file" | "sha256" | "renderedAt">> => {
  const output = await run([
    "ffprobe",
    "-v",
    "error",
    "-show_entries",
    "stream=index,codec_type,codec_name,width,height,r_frame_rate:format=duration,size",
    "-of",
    "json",
    path,
  ]);
  const probe = JSON.parse(output) as {
    streams?: {codec_type?: string; codec_name?: string; width?: number; height?: number; r_frame_rate?: string}[];
    format?: {duration?: string; size?: string};
  };
  const streams = probe.streams ?? [];
  const videos = streams.filter(({codec_type}) => codec_type === "video");
  const audioStreams = streams.filter(({codec_type}) => codec_type === "audio").length;
  const video = videos[0];
  const durationSeconds = Number(probe.format?.duration);
  if (
    videos.length !== 1 ||
    audioStreams !== 0 ||
    video?.codec_name !== "h264" ||
    video.width !== FRAME.width ||
    video.height !== FRAME.height ||
    video.r_frame_rate !== "30/1" ||
    !Number.isFinite(durationSeconds) ||
    Math.abs(durationSeconds - expectedSeconds) > 0.2
  ) {
    throw new Error(
      `rendered transitions do not satisfy the silent H.264 contract at ${FRAME.width}x${FRAME.height} (${durationSeconds}s against ${expectedSeconds}s)`,
    );
  }
  return {
    codec: "h264",
    width: video.width,
    height: video.height,
    frameRate: "30/1",
    durationSeconds,
    sizeBytes: Number(probe.format?.size),
    audioStreams: 0,
  };
};

export type TransitionRenderOptions = Readonly<{
  browser: Browser;
  manifestBytes: Uint8Array;
  captureDirectory: string;
  outputDirectory: string;
  captureKind: CaptureReportKind;
  now: Date;
}>;

export const renderTransitions = async (
  options: TransitionRenderOptions,
): Promise<{path: string; plan: readonly Transition[]; report: TransitionRenderReport}> => {
  const manifestSnapshot = Uint8Array.from(options.manifestBytes);
  const manifestSha256 = sha256(manifestSnapshot);
  let manifest: CaptureManifest;
  try {
    manifest = parseManifest(JSON.parse(Buffer.from(manifestSnapshot).toString("utf8")));
  } catch (error) {
    throw new Error(`manifest validation failed: ${error instanceof Error ? error.message : String(error)}`);
  }

  const captureDirectory = await canonicalDirectory(options.captureDirectory, "capture directory");
  const checkpointDirectory = await canonicalDirectory(join(captureDirectory, "checkpoints"), "checkpoint directory");
  if (!containedBy(captureDirectory, checkpointDirectory)) throw new Error("checkpoint directory escapes the capture directory");
  const domDirectory = await canonicalDirectory(join(captureDirectory, "dom"), "DOM directory");
  if (!containedBy(captureDirectory, domDirectory)) throw new Error("DOM directory escapes the capture directory");

  const reportBytes = await readRegularFile(captureDirectory, join(captureDirectory, "report.json"), "capture report");
  const reportSha256 = sha256(reportBytes);
  let report: PendingReport<CaptureReportKind>;
  try {
    report = parsePendingReport(JSON.parse(Buffer.from(reportBytes).toString("utf8")), options.captureKind, {
      // A capture whose montage was already rendered is still valid evidence to
      // re-frame; the transition render never writes back into it.
      allowRendered: true,
    });
  } catch (error) {
    throw new Error(`report validation failed: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (report.source.manifestSha256 !== manifestSha256) {
    throw new Error("capture report does not identify the supplied manifest bytes");
  }
  if (report.slug !== manifest.slug) throw new Error("capture report is for another manifest");

  const isStateSequence = options.captureKind.includes("state-sequence");
  const states = isStateSequence ? identifyWatchedStates(manifest, report) : identifyCheckpointStates(manifest, report);

  const expectedNames = report.checkpoints.map(({file}) => basename(file)).sort();
  const observedNames = (await readdir(checkpointDirectory, {withFileTypes: true}))
    .filter(({name}) => name.endsWith(".png"))
    .map(({name}) => name)
    .sort();
  if (expectedNames.length !== observedNames.length || expectedNames.some((name, index) => name !== observedNames[index])) {
    throw new Error("checkpoint directory contains an unreported PNG input");
  }
  const expectedDomNames = report.checkpoints.flatMap(({dom}) => [basename(dom.before.file), basename(dom.after.file)]).sort();
  const observedDomNames = (await readdir(domDirectory, {withFileTypes: true}))
    .filter(({name}) => name.endsWith(".html"))
    .map(({name}) => name)
    .sort();
  if (
    expectedDomNames.length !== observedDomNames.length ||
    expectedDomNames.some((name, index) => name !== observedDomNames[index])
  ) {
    throw new Error("DOM directory contains an unreported HTML input");
  }

  const verifiedInputs: Uint8Array[] = [];
  for (const checkpoint of report.checkpoints) {
    const bytes = await readRegularFile(captureDirectory, join(captureDirectory, checkpoint.file), `state ${checkpoint.id}`);
    if (sha256(bytes) !== checkpoint.sha256) throw new Error(`state ${checkpoint.id} hash does not match the report`);
    const observed = pngDimensions(bytes, `state ${checkpoint.id} still`);
    if (observed.width !== checkpoint.dimensions.width || observed.height !== checkpoint.dimensions.height) {
      throw new Error(`state ${checkpoint.id} still is cropped against its recorded scrollHeight`);
    }
    for (const phase of ["before", "after"] as const) {
      const dom = checkpoint.dom[phase];
      const domBytes = await readRegularFile(captureDirectory, join(captureDirectory, dom.file), `state ${checkpoint.id} ${phase} DOM`);
      if (sha256(domBytes) !== dom.sha256 || domBytes.byteLength !== dom.byteLength) {
        throw new Error(`state ${checkpoint.id} ${phase} DOM does not match the report`);
      }
    }
    verifiedInputs.push(bytes);
  }

  await requireAbsent(options.outputDirectory, "transition output directory");
  const stagingDirectory = await realpath(await mkdtemp(`${options.outputDirectory}.staging-`));
  try {
    const stagedStills: string[] = [];
    for (const [index, bytes] of verifiedInputs.entries()) {
      const path = join(stagingDirectory, `still-${index}.png`);
      await writeFile(path, bytes, {flag: "wx", mode: 0o600});
      stagedStills.push(path);
    }
    const rasters = await Promise.all(
      stagedStills.map((path, index) => decodeRgba(path, report.checkpoints[index].dimensions, `state ${states[index].id}`)),
    );
    const plan = planTransitions(states, rasters, EVIDENCE_PANE);

    const captionPaths: string[] = [];
    for (const transition of plan) {
      const path = join(stagingDirectory, `caption-${transition.index}.png`);
      await writeFile(path, await renderCaptionStrip(options.browser, transition.caption), {flag: "wx", mode: 0o600});
      captionPaths.push(path);
    }

    const ffmpeg = ["ffmpeg", "-loglevel", "error", "-y"];
    const filters: string[] = [];
    const segments: string[] = [];
    for (const [position, transition] of plan.entries()) {
      const base = position * 3;
      const {window: crop, canvas} = transition;
      const padWidth = Math.max(canvas.width, EVIDENCE_PANE.width);
      const padHeight = Math.max(canvas.height, EVIDENCE_PANE.height);
      const departing = transition.leadSeconds + transition.crossfadeSeconds;
      const arriving = transition.crossfadeSeconds + transition.holdSeconds;
      ffmpeg.push("-loop", "1", "-framerate", "30", "-t", departing.toFixed(4), "-i", stagedStills[transition.index]);
      ffmpeg.push("-loop", "1", "-framerate", "30", "-t", arriving.toFixed(4), "-i", stagedStills[transition.index + 1]);
      ffmpeg.push(
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        (departing + transition.holdSeconds).toFixed(4),
        "-i",
        captionPaths[position],
      );
      // Crop, never scale: the changed content stays at the size the browser
      // rendered it, which is the only way it stays readable.
      const evidence =
        `pad=${padWidth}:${padHeight}:0:0:black,` +
        `crop=${crop.width}:${crop.height}:${crop.x}:${crop.y},` +
        `pad=${EVIDENCE_PANE.width}:${EVIDENCE_PANE.height}:(ow-iw)/2:(oh-ih)/2:black,` +
        `setsar=1,fps=30,format=rgba`;
      filters.push(`[${base}:v]${evidence}[a${position}]`);
      filters.push(`[${base + 1}:v]${evidence}[b${position}]`);
      filters.push(
        `[a${position}][b${position}]xfade=transition=fade:duration=${transition.crossfadeSeconds.toFixed(4)}:offset=${transition.leadSeconds.toFixed(4)}[e${position}]`,
      );
      filters.push(`[${base + 2}:v]setsar=1,fps=30,format=rgba[c${position}]`);
      filters.push(`[e${position}][c${position}]vstack=inputs=2[s${position}]`);
      segments.push(`[s${position}]`);
    }
    const temporaryVideo = join(stagingDirectory, "transitions.mp4");
    ffmpeg.push(
      "-filter_complex",
      `${filters.join(";")};${segments.join("")}concat=n=${plan.length}:v=1:a=0,format=yuv420p[out]`,
      "-map",
      "[out]",
      "-c:v",
      "libx264",
      "-preset",
      "medium",
      "-crf",
      "20",
      "-pix_fmt",
      "yuv420p",
      "-r",
      "30",
      "-an",
      "-movflags",
      "+faststart",
      temporaryVideo,
    );
    await run(ffmpeg);

    const probed = await probeVideo(temporaryVideo, planSeconds(plan));
    const videoBytes = await readRegularFile(stagingDirectory, temporaryVideo, "rendered transitions");
    const provenance = options.captureKind.startsWith("github-live") ? "live" : "fixture";
    const videoName = `hamsterdan-${manifest.slug}-${provenance}-transitions.mp4`;
    const video: VideoReport = {file: videoName, sha256: sha256(videoBytes), renderedAt: options.now.toISOString(), ...probed};
    const renderReport: TransitionRenderReport = {
      schema: 1,
      kind: "github-live-transition-render",
      slug: manifest.slug,
      renderedAt: options.now.toISOString(),
      source: {
        captureKind: options.captureKind,
        capturedAt: report.capturedAt,
        gitCommit: report.source.gitCommit,
        manifestSha256,
        reportSha256,
      },
      frame: FRAME,
      captionHeight: CAPTION_HEIGHT,
      transitions: plan,
      video,
    };
    const renderReportBytes = `${JSON.stringify(renderReport, null, 2)}\n`;
    await writeFile(join(stagingDirectory, "transitions.json"), renderReportBytes, {flag: "wx"});
    await writeFile(
      join(stagingDirectory, "SHA256SUMS"),
      `${[`${video.sha256}  ${video.file}`, `${sha256(renderReportBytes)}  transitions.json`].join("\n")}\n`,
      {flag: "wx"},
    );
    for (const path of [...stagedStills, ...captionPaths]) await rm(path);
    await rename(temporaryVideo, join(stagingDirectory, videoName));
    await mkdir(join(options.outputDirectory, ".."), {recursive: true});
    await rename(stagingDirectory, options.outputDirectory);
    return {path: join(options.outputDirectory, videoName), plan, report: renderReport};
  } catch (error) {
    await rm(stagingDirectory, {recursive: true, force: true});
    throw error;
  }
};
