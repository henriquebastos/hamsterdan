import {createHash} from "node:crypto";
import {constants} from "node:fs";
import {lstat, mkdtemp, open, readdir, realpath, rename, rm, writeFile} from "node:fs/promises";
import {basename, isAbsolute, join, relative, sep} from "node:path";
import {expectedStillHeight} from "./capture";
import {parseManifest, type CaptureManifest} from "./manifest";
import {pngDimensions} from "./png";
import type {Region} from "./region";

export type VideoReport = Readonly<{
  file: string;
  sha256: string;
  renderedAt: string;
  codec: "h264";
  width: number;
  height: number;
  frameRate: "30/1";
  durationSeconds: number;
  sizeBytes: number;
  audioStreams: 0;
}>;

export type ReportDom = Readonly<{file: string; sha256: string; byteLength: number}>;

export type ReportCheckpoint = Readonly<{
  id: string;
  kind: string;
  target: string;
  requestedUrl: string;
  finalUrl: string;
  capturedAt: string;
  file: string;
  sha256: string;
  dimensions: Readonly<{width: number; height: number}>;
  capture: Readonly<{fullPage: true; scrollHeight: number; attempts: number}>;
  dom: Readonly<{before: ReportDom; after: ReportDom}>;
  anchor: Region | null;
  scope: Readonly<{normalizedTextLength: number; normalizedTextSha256: string}>;
  assertions: readonly Readonly<{id: string; matched: true; expectedSha256: string}>[];
}>;

export type CheckpointCaptureKind = "github-live-checkpoint-capture" | "github-fixture-checkpoint-capture";

export type StateSequenceCaptureKind =
  | "github-live-state-sequence-capture"
  | "github-fixture-state-sequence-capture";

export type CaptureReportKind = CheckpointCaptureKind | StateSequenceCaptureKind;

export type PendingReport<Kind extends CaptureReportKind> = Readonly<{
  schema: 1;
  kind: Kind;
  slug: string;
  capturedAt: string;
  source: Readonly<{gitCommit: string; clean: true; manifestSha256: string}>;
  runtime: Readonly<Record<string, unknown>>;
  checkpoints: readonly ReportCheckpoint[];
  video: null;
}>;

const REPORT_KEYS = ["schema", "kind", "slug", "capturedAt", "source", "runtime", "checkpoints", "video"];
const SOURCE_KEYS = ["gitCommit", "clean", "manifestSha256"];
const RUNTIME_KEYS = [
  "bunVersion",
  "playwrightVersion",
  "browserVersion",
  "viewport",
  "deviceScaleFactor",
  "locale",
  "timezoneId",
  "colorScheme",
  "reducedMotion",
];
const CHECKPOINT_KEYS = [
  "id",
  "kind",
  "target",
  "requestedUrl",
  "finalUrl",
  "capturedAt",
  "file",
  "sha256",
  "dimensions",
  "capture",
  "dom",
  "anchor",
  "scope",
  "assertions",
];

export const record = (value: unknown, label: string): Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error(`${label} is invalid`);
  return value as Record<string, unknown>;
};

export const exactKeys = (
  value: Record<string, unknown>,
  expected: readonly string[],
  label: string,
  optional: readonly string[] = [],
): void => {
  const actual = Object.keys(value)
    .filter((key) => !optional.includes(key))
    .sort();
  const keys = [...expected].sort();
  if (actual.length !== keys.length || actual.some((key, index) => key !== keys[index])) {
    throw new Error(`${label} has an unknown or missing field`);
  }
};

export const string = (value: unknown, pattern: RegExp, label: string): string => {
  if (typeof value !== "string" || !pattern.test(value)) throw new Error(`${label} is invalid`);
  return value;
};

export const integer = (value: unknown, label: string): number => {
  if (!Number.isInteger(value) || (value as number) < 0) throw new Error(`${label} is invalid`);
  return value as number;
};

export const parseAnchor = (raw: unknown, label: string): Region | null => {
  if (raw === undefined || raw === null) return null;
  const value = record(raw, label);
  exactKeys(value, ["x", "y", "width", "height"], label);
  const anchor = {
    x: integer(value.x, `${label} x`),
    y: integer(value.y, `${label} y`),
    width: integer(value.width, `${label} width`),
    height: integer(value.height, `${label} height`),
  };
  if (anchor.width === 0 || anchor.height === 0) throw new Error(`${label} is empty`);
  return anchor;
};

export const parsePendingReport = <Kind extends CaptureReportKind>(
  raw: unknown,
  expectedKind: Kind,
  // A montage renderer may only complete a pending capture. A transition
  // render reads a capture without writing to it, so it also accepts one whose
  // montage was already rendered.
  options: Readonly<{allowRendered?: boolean}> = {},
): PendingReport<Kind> => {
  const value = record(raw, "report");
  exactKeys(value, REPORT_KEYS, "report");
  const videoAcceptable = value.video === null || (options.allowRendered === true && typeof value.video === "object");
  if (value.schema !== 1 || value.kind !== expectedKind || !videoAcceptable) {
    throw new Error(`report is not a pending ${expectedKind.startsWith("github-live") ? "live" : "fixture"} capture`);
  }
  const source = record(value.source, "report source");
  exactKeys(source, SOURCE_KEYS, "report source");
  const runtime = record(value.runtime, "report runtime");
  exactKeys(runtime, RUNTIME_KEYS, "report runtime");
  const viewport = record(runtime.viewport, "report viewport");
  exactKeys(viewport, ["width", "height"], "report viewport");
  const width = integer(viewport.width, "report viewport width");
  const height = integer(viewport.height, "report viewport height");

  if (!Array.isArray(value.checkpoints) || value.checkpoints.length === 0) {
    throw new Error("report checkpoints are invalid");
  }
  const checkpoints = value.checkpoints.map((rawCheckpoint, index): ReportCheckpoint => {
    const checkpoint = record(rawCheckpoint, `report checkpoint ${index}`);
    // A capture recorded before anchor boxes existed carries no anchor; the
    // transition renderer falls back to a page walk for it.
    exactKeys(checkpoint, CHECKPOINT_KEYS.filter((key) => key !== "anchor"), `report checkpoint ${index}`, ["anchor"]);
    const dimensions = record(checkpoint.dimensions, `report checkpoint ${index} dimensions`);
    exactKeys(dimensions, ["width", "height"], `report checkpoint ${index} dimensions`);
    const scope = record(checkpoint.scope, `report checkpoint ${index} scope`);
    exactKeys(scope, ["normalizedTextLength", "normalizedTextSha256"], `report checkpoint ${index} scope`);
    if (!Array.isArray(checkpoint.assertions) || checkpoint.assertions.length === 0) {
      throw new Error(`report checkpoint ${index} assertions are invalid`);
    }
    const assertions = checkpoint.assertions.map((rawAssertion, assertionIndex) => {
      const item = record(rawAssertion, `report checkpoint ${index} assertion ${assertionIndex}`);
      exactKeys(item, ["id", "matched", "expectedSha256"], `report checkpoint ${index} assertion ${assertionIndex}`);
      if (item.matched !== true) throw new Error(`report checkpoint ${index} contains an unmatched assertion`);
      return {
        id: string(item.id, /^[a-z0-9]+(?:-[a-z0-9]+)*$/, "assertion id"),
        matched: true as const,
        expectedSha256: string(item.expectedSha256, /^[0-9a-f]{64}$/, "assertion hash"),
      };
    });
    const captureBlock = record(checkpoint.capture, `report checkpoint ${index} capture`);
    exactKeys(captureBlock, ["fullPage", "scrollHeight", "attempts"], `report checkpoint ${index} capture`);
    if (captureBlock.fullPage !== true) {
      throw new Error(`report checkpoint ${index} is not a full-page capture`);
    }
    const scrollHeight = integer(captureBlock.scrollHeight, `report checkpoint ${index} scroll height`);
    const attempts = integer(captureBlock.attempts, `report checkpoint ${index} capture attempts`);
    if (scrollHeight === 0 || attempts === 0) {
      throw new Error(`report checkpoint ${index} capture is invalid`);
    }
    const observedWidth = integer(dimensions.width, `report checkpoint ${index} width`);
    const observedHeight = integer(dimensions.height, `report checkpoint ${index} height`);
    if (observedWidth !== width) {
      throw new Error(`report checkpoint ${index} width differs from the viewport`);
    }
    if (observedHeight !== expectedStillHeight(scrollHeight, height)) {
      throw new Error(`report checkpoint ${index} height is cropped against its recorded scrollHeight`);
    }

    const id = string(checkpoint.id, /^[a-z0-9]+(?:-[a-z0-9]+)*$/, "checkpoint id");
    const domBlock = record(checkpoint.dom, `report checkpoint ${index} dom`);
    exactKeys(domBlock, ["before", "after"], `report checkpoint ${index} dom`);
    const dom = Object.fromEntries(
      (["before", "after"] as const).map((phase) => {
        const entry = record(domBlock[phase], `report checkpoint ${index} ${phase} DOM`);
        exactKeys(entry, ["file", "sha256", "byteLength"], `report checkpoint ${index} ${phase} DOM`);
        const byteLength = integer(entry.byteLength, `report checkpoint ${index} ${phase} DOM size`);
        if (byteLength === 0) throw new Error(`report checkpoint ${index} ${phase} DOM is empty`);
        return [
          phase,
          {
            file: string(entry.file, new RegExp(`^dom/${id}\\.${phase}\\.html$`), `checkpoint ${phase} DOM file`),
            sha256: string(entry.sha256, /^[0-9a-f]{64}$/, `checkpoint ${phase} DOM hash`),
            byteLength,
          },
        ];
      }),
    ) as {before: ReportDom; after: ReportDom};

    const kind = string(
      checkpoint.kind,
      /^(?:issue-comment|review|commit|pr-checks|actions-run|actions-attempt|state)$/,
      "checkpoint kind",
    );
    return {
      id,
      anchor: parseAnchor(checkpoint.anchor, `report checkpoint ${index} anchor`),
      kind,
      target: string(
        checkpoint.target,
        kind === "actions-attempt" ? /^[1-9][0-9]{0,19}\/attempts\/[1-9][0-9]{0,4}$/ : /^[0-9a-f]+$/,
        "checkpoint target",
      ),
      requestedUrl: string(checkpoint.requestedUrl, /^https:\/\/github\.com\//, "requested URL"),
      finalUrl: string(checkpoint.finalUrl, /^https:\/\/github\.com\//, "final URL"),
      capturedAt: string(checkpoint.capturedAt, /^\d{4}-\d{2}-\d{2}T/, "checkpoint instant"),
      file: string(checkpoint.file, /^checkpoints\/[a-z0-9]+(?:-[a-z0-9]+)*\.png$/, "checkpoint file"),
      sha256: string(checkpoint.sha256, /^[0-9a-f]{64}$/, "checkpoint hash"),
      dimensions: {width: observedWidth, height: observedHeight},
      capture: {fullPage: true, scrollHeight, attempts},
      dom,
      scope: {
        normalizedTextLength: integer(scope.normalizedTextLength, "scope text length"),
        normalizedTextSha256: string(scope.normalizedTextSha256, /^[0-9a-f]{64}$/, "scope hash"),
      },
      assertions,
    };
  });

  return {
    schema: 1,
    kind: expectedKind,
    slug: string(value.slug, /^[a-z0-9]+(?:-[a-z0-9]+)*$/, "report slug"),
    capturedAt: string(value.capturedAt, /^\d{4}-\d{2}-\d{2}T/, "capture instant"),
    source: {
      gitCommit: string(source.gitCommit, /^[0-9a-f]{40}$/, "source commit"),
      clean: source.clean === true ? true : (() => { throw new Error("source is dirty"); })(),
      manifestSha256: string(source.manifestSha256, /^[0-9a-f]{64}$/, "manifest hash"),
    },
    runtime,
    checkpoints,
    video: null,
  };
};

export const sha256 = (value: Uint8Array | string): string => createHash("sha256").update(value).digest("hex");

export const containedBy = (root: string, candidate: string): boolean => {
  const path = relative(root, candidate);
  return path !== "" && !isAbsolute(path) && path !== ".." && !path.startsWith(`..${sep}`);
};

export const canonicalDirectory = async (path: string, label: string): Promise<string> => {
  const metadata = await lstat(path);
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) throw new Error(`${label} must be a non-symlink directory`);
  return realpath(path);
};

export const readRegularFile = async (root: string, path: string, label: string): Promise<Uint8Array> => {
  const metadata = await lstat(path);
  if (metadata.isSymbolicLink() || !metadata.isFile()) throw new Error(`${label} must be a non-symlink regular file`);
  const canonical = await realpath(path);
  if (!containedBy(root, canonical)) throw new Error(`${label} escapes the capture directory`);

  let handle;
  try {
    handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  } catch (error) {
    throw new Error(`${label} could not be opened without following a symlink: ${error instanceof Error ? error.message : String(error)}`);
  }
  try {
    if (!(await handle.stat()).isFile()) throw new Error(`${label} must remain a regular file`);
    return await handle.readFile();
  } finally {
    await handle.close();
  }
};

export const requireAbsent = async (path: string, label: string): Promise<void> => {
  try {
    const metadata = await lstat(path);
    const kind = metadata.isSymbolicLink() ? "symlink" : "existing path";
    throw new Error(`${label} is already present as a ${kind}`);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
};

export const run = async (arguments_: string[]): Promise<string> => {
  const child = Bun.spawn(arguments_, {stdout: "pipe", stderr: "pipe"});
  const [stdout, stderr, exit] = await Promise.all([
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
    child.exited,
  ]);
  if (exit !== 0) throw new Error(`${arguments_[0]} failed: ${stderr.slice(0, 2000)}`);
  return stdout;
};

const probeVideo = async (path: string, manifest: CaptureManifest): Promise<Omit<VideoReport, "file" | "sha256" | "renderedAt">> => {
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
  const expectedDuration = manifest.checkpoints.reduce((total, {holdSeconds}) => total + holdSeconds, 0);
  if (
    videos.length !== 1 ||
    audioStreams !== 0 ||
    video?.codec_name !== "h264" ||
    video.width !== manifest.viewport.width ||
    video.height !== manifest.viewport.height ||
    video.r_frame_rate !== "30/1" ||
    !Number.isFinite(durationSeconds) ||
    Math.abs(durationSeconds - expectedDuration) > 0.1
  ) {
    throw new Error("rendered video does not satisfy the silent H.264 contract");
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

const renderCapturedEvidence = async <Kind extends CaptureReportKind>(
  manifestBytes: Uint8Array,
  directory: string,
  now: Date,
  expectedKind: Kind,
): Promise<{path: string; video: VideoReport}> => {
  const manifestSnapshot = Uint8Array.from(manifestBytes);
  const manifestSha256 = sha256(manifestSnapshot);
  let manifest: CaptureManifest;
  try {
    manifest = parseManifest(JSON.parse(Buffer.from(manifestSnapshot).toString("utf8")));
  } catch (error) {
    throw new Error(`manifest validation failed: ${error instanceof Error ? error.message : String(error)}`);
  }

  const captureDirectory = await canonicalDirectory(directory, "capture directory");
  const checkpointDirectory = await canonicalDirectory(join(captureDirectory, "checkpoints"), "checkpoint directory");
  if (!containedBy(captureDirectory, checkpointDirectory)) throw new Error("checkpoint directory escapes the capture directory");
  const domDirectory = await canonicalDirectory(join(captureDirectory, "dom"), "DOM directory");
  if (!containedBy(captureDirectory, domDirectory)) throw new Error("DOM directory escapes the capture directory");
  const reportPath = join(captureDirectory, "report.json");
  let report: PendingReport<Kind>;
  try {
    const reportBytes = await readRegularFile(captureDirectory, reportPath, "capture report");
    report = parsePendingReport(JSON.parse(Buffer.from(reportBytes).toString("utf8")), expectedKind);
  } catch (error) {
    throw new Error(`report validation failed: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (report.source.manifestSha256 !== manifestSha256) {
    throw new Error("capture report does not identify the supplied manifest bytes");
  }
  if (report.slug !== manifest.slug || report.checkpoints.length !== manifest.checkpoints.length) {
    throw new Error("report order does not match the manifest");
  }

  for (const [index, checkpoint] of manifest.checkpoints.entries()) {
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
  }

  const expectedNames = report.checkpoints.map(({file}) => basename(file)).sort();
  const observedEntries = await readdir(checkpointDirectory, {withFileTypes: true});
  const observedNames = observedEntries.filter(({name}) => name.endsWith(".png")).map(({name}) => name).sort();
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
    const bytes = await readRegularFile(captureDirectory, join(captureDirectory, checkpoint.file), `checkpoint ${checkpoint.id}`);
    const observedHash = sha256(bytes);
    if (observedHash !== checkpoint.sha256) throw new Error(`checkpoint ${checkpoint.id} hash does not match the report`);
    const observed = pngDimensions(bytes, `checkpoint ${checkpoint.id} still`);
    if (observed.width !== checkpoint.dimensions.width || observed.height !== checkpoint.dimensions.height) {
      throw new Error(`checkpoint ${checkpoint.id} still is cropped against its recorded scrollHeight`);
    }
    for (const phase of ["before", "after"] as const) {
      const dom = checkpoint.dom[phase];
      const domBytes = await readRegularFile(
        captureDirectory,
        join(captureDirectory, dom.file),
        `checkpoint ${checkpoint.id} ${phase} DOM`,
      );
      if (sha256(domBytes) !== dom.sha256 || domBytes.byteLength !== dom.byteLength) {
        throw new Error(`checkpoint ${checkpoint.id} ${phase} DOM does not match the report`);
      }
    }
    verifiedInputs.push(bytes);
  }

  const provenance = expectedKind === "github-live-checkpoint-capture" ? "live" : "fixture";
  const videoName = `hamsterdan-${manifest.slug}-${provenance}-checkpoints.mp4`;
  const finalPath = join(captureDirectory, videoName);
  const sumsPath = join(captureDirectory, "SHA256SUMS");
  await requireAbsent(finalPath, "rendered video path");
  await requireAbsent(sumsPath, "checksum path");
  const stagingDirectory = await mkdtemp(join(captureDirectory, ".render-staging-"));

  try {
    const stagedInputs: string[] = [];
    for (const [index, bytes] of verifiedInputs.entries()) {
      const path = join(stagingDirectory, `${index}.png`);
      await writeFile(path, bytes, {flag: "wx", mode: 0o600});
      stagedInputs.push(path);
    }

    const temporaryPath = join(stagingDirectory, "video.mp4");
    const ffmpeg = ["ffmpeg", "-loglevel", "error", "-y"];
    for (const [index, checkpoint] of manifest.checkpoints.entries()) {
      ffmpeg.push(
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        String(checkpoint.holdSeconds),
        "-i",
        stagedInputs[index],
      );
    }
    // Checkpoint stills are full-page, so each one is taller than the montage
    // canvas. Fit the whole page inside the frame; never crop it back.
    const {width, height} = manifest.viewport;
    const fit =
      `scale=${width}:${height}:force_original_aspect_ratio=decrease,` +
      `pad=${width}:${height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p`;
    const inputs = manifest.checkpoints.map((_, index) => `[${index}:v]${fit}[v${index}]`).join(";");
    const concat = manifest.checkpoints.map((_, index) => `[v${index}]`).join("");
    ffmpeg.push(
      "-filter_complex",
      `${inputs};${concat}concat=n=${manifest.checkpoints.length}:v=1:a=0[out]`,
      "-map",
      "[out]",
      "-c:v",
      "libx264",
      "-preset",
      "medium",
      "-crf",
      "22",
      "-pix_fmt",
      "yuv420p",
      "-r",
      "30",
      "-an",
      "-movflags",
      "+faststart",
      temporaryPath,
    );

    await run(ffmpeg);
    const probed = await probeVideo(temporaryPath, manifest);
    const videoBytes = await readRegularFile(stagingDirectory, temporaryPath, "rendered video");
    const video: VideoReport = {
      file: videoName,
      sha256: sha256(videoBytes),
      renderedAt: now.toISOString(),
      ...probed,
    };
    const completedReport = {...report, video};
    const reportBytes = `${JSON.stringify(completedReport, null, 2)}\n`;
    const reportTemporary = join(stagingDirectory, "report.json");
    const sumsTemporary = join(stagingDirectory, "SHA256SUMS");
    const sums = [
      ...report.checkpoints.flatMap(({sha256: digest, file, dom}) => [
        `${dom.before.sha256}  ${dom.before.file}`,
        `${digest}  ${file}`,
        `${dom.after.sha256}  ${dom.after.file}`,
      ]),
      `${video.sha256}  ${video.file}`,
      `${sha256(reportBytes)}  report.json`,
    ].join("\n");
    await writeFile(reportTemporary, reportBytes, {flag: "wx"});
    await writeFile(sumsTemporary, `${sums}\n`, {flag: "wx"});
    await rename(temporaryPath, finalPath);
    await rename(sumsTemporary, sumsPath);
    await rename(reportTemporary, reportPath);
    return {path: finalPath, video};
  } finally {
    await rm(stagingDirectory, {recursive: true, force: true});
  }
};

export const renderEvidence = (
  manifestBytes: Uint8Array,
  directory: string,
  now: Date,
): Promise<{path: string; video: VideoReport}> =>
  renderCapturedEvidence(manifestBytes, directory, now, "github-live-checkpoint-capture");

export const renderFixtureEvidence = (
  manifestBytes: Uint8Array,
  directory: string,
  now: Date,
): Promise<{path: string; video: VideoReport}> =>
  renderCapturedEvidence(manifestBytes, directory, now, "github-fixture-checkpoint-capture");
