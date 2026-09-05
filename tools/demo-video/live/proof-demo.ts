import {mkdir, readFile, writeFile} from "node:fs/promises";
import {join, resolve} from "node:path";
import {chromium} from "playwright";
import {readingSeconds} from "../src/timing";
import {pngDimensions} from "./png";
import {canonicalDirectory, readRegularFile, run, sha256} from "./render";
import {CAPTION_HEIGHT, EVIDENCE_PANE, FRAME, renderCaptionStrip} from "./transition-render";
import {CROSSFADE_SECONDS} from "./transition";

export type Shot = {id: string; source: string; yFrom: number; yTo: number; seconds: number; caption: string};
type Reference = {path: string; sha256: string};
type Storyboard = {schema: 1; kind: "recovered-proof-demo"; slug: string; recoveryManifest: Reference; proofManifest: Reference; shots: Shot[]};
type Recovery = {pages: {output: string; sha256: string; offlinePngSha256: string}[]};

export const validateShot = (shot: Shot, width: number, height: number): void => {
  if (!/^[a-z0-9-]+$/.test(shot.id) || typeof shot.caption !== "string" || !shot.caption.trim() || shot.caption.length > 115) {
    throw new Error("Shot identity or caption is invalid");
  }
  if (width !== EVIDENCE_PANE.width || ![shot.yFrom, shot.yTo].every((y) => Number.isInteger(y) && y >= 0 && y + EVIDENCE_PANE.height <= height)) {
    throw new Error(`Shot ${shot.id} would crop beyond its evidence`);
  }
  if (!Number.isInteger(shot.seconds) || shot.seconds < Math.max(4, readingSeconds(shot.caption) + CROSSFADE_SECONDS) || shot.seconds > 30) {
    throw new Error(`Shot ${shot.id} does not leave enough reading time`);
  }
};

export const verifyDigest = (bytes: Uint8Array, expected: string, label: string): void => {
  if (sha256(bytes) !== expected) throw new Error(`${label} no longer matches its recorded hash`);
};

const cropPosition = (shot: Shot, progress: number): number =>
  Math.round(shot.yFrom + (shot.yTo - shot.yFrom) * progress * progress * (3 - 2 * progress));

export const renderProofDemo = async (manifestPath: string, output: string, mode: "stills" | "render"): Promise<void> => {
  const root = await canonicalDirectory(resolve(import.meta.dir, "../../.."), "repository");
  const bytes = await readRegularFile(root, resolve(manifestPath), "storyboard");
  const storyboard = JSON.parse(Buffer.from(bytes).toString()) as Storyboard;
  if (storyboard.schema !== 1 || storyboard.kind !== "recovered-proof-demo" || !/^[a-z0-9-]+$/.test(storyboard.slug) || !Array.isArray(storyboard.shots) || storyboard.shots.length < 2 || storyboard.shots.length > 24) {
    throw new Error("Invalid recovered-proof storyboard");
  }
  const sources = [];
  for (const reference of [storyboard.recoveryManifest, storyboard.proofManifest]) {
    const data = await readRegularFile(root, join(root, reference.path), "proof manifest");
    verifyDigest(data, reference.sha256, reference.path);
    sources.push(JSON.parse(Buffer.from(data).toString()));
  }
  const recovery = sources[0] as Recovery;
  await mkdir(output, {recursive: true});
  const assets = join(output, "assets");
  const previews = join(output, "previews");
  await mkdir(assets, {recursive: true});
  await mkdir(previews, {recursive: true});
  const browser = await chromium.launch();
  const shotFiles: {image: string; caption: string; source: string; sha256: string}[] = [];
  try {
    let previousStage = 0;
    const ids = new Set<string>();
    for (const shot of storyboard.shots) {
      if (ids.has(shot.id) || !/^\d{2}-[a-z-]+(?:\.(?:before|after))?\.html$/.test(shot.source)) throw new Error("Invalid or duplicate shot");
      ids.add(shot.id);
      const stage = Number(shot.source.slice(0, 2));
      if (stage < previousStage) throw new Error("Storyboard reverses the observed journey");
      previousStage = stage;
      const page = recovery.pages.find((page) => page.output.endsWith(`/pr83/${shot.source}`));
      if (!page) throw new Error(`Unreported source ${shot.source}`);
      const html = await readRegularFile(root, join(root, page.output), shot.source);
      verifyDigest(html, page.sha256, shot.source);
      const png = await readRegularFile(root, join(root, `${page.output}.png`), shot.id);
      verifyDigest(png, page.offlinePngSha256, shot.id);
      const dimensions = pngDimensions(png, shot.id);
      validateShot(shot, dimensions.width, dimensions.height);
      const image = join(assets, `${shot.id}.png`);
      const caption = join(assets, `${shot.id}-caption.png`);
      await writeFile(image, png);
      await writeFile(caption, await renderCaptionStrip(browser, shot.caption));
      shotFiles.push({image, caption, source: page.output, sha256: page.offlinePngSha256});
    }
  } finally {
    await browser.close();
  }
  const visualFilter = (y: string): string =>
    `[0:v]crop=${EVIDENCE_PANE.width}:${EVIDENCE_PANE.height}:0:'${y}',setsar=1[e];[e][1:v]vstack=inputs=2,format=yuv420p[out]`;
  const manifestSha256 = sha256(bytes);
  if (mode === "stills") {
    const files = [];
    for (const [i, shot] of storyboard.shots.entries()) {
      for (const [name, progress] of [["start", 0], ["middle", 0.5], ["end", 1]] as const) {
        const path = join(previews, `${shot.id}-${name}.png`);
        await run(["ffmpeg", "-v", "error", "-y", "-filter_complex_threads", "1", "-i", shotFiles[i].image, "-i", shotFiles[i].caption,
          "-filter_complex", visualFilter(String(cropPosition(shot, progress))), "-map", "[out]", "-frames:v", "1", path]);
        files.push({file: path, sha256: sha256(await readFile(path))});
      }
    }
    await writeFile(join(output, "stills.json"), JSON.stringify({manifestSha256, files}, null, 2) + "\n");
    console.log(`Prepared ${files.length} previews for inspection`);
    return;
  }
  const preview = JSON.parse(await readFile(join(output, "stills.json"), "utf8"));
  if (preview.manifestSha256 !== manifestSha256) throw new Error("Regenerate and inspect previews for this storyboard");
  for (const file of preview.files) verifyDigest(await readFile(file.file), file.sha256, "preview");
  const segments = [];
  for (const [i, shot] of storyboard.shots.entries()) {
    const path = join(output, `${shot.id}.mp4`);
    // Pause at both ends of the pan; move only the recorded pixels, at 1:1.
    const progress = `min(1,max(0,(t-2)/${shot.seconds - 4}))`;
    const y = `${shot.yFrom}+(${shot.yTo - shot.yFrom})*${progress}*${progress}*(3-2*${progress})`;
    await run(["ffmpeg", "-v", "error", "-y", "-filter_complex_threads", "1", "-loop", "1", "-framerate", "30", "-i", shotFiles[i].image,
      "-loop", "1", "-framerate", "30", "-i", shotFiles[i].caption, "-filter_complex", visualFilter(y), "-map", "[out]",
      "-t", String(shot.seconds), "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-threads", "4", "-r", "30", "-an", path]);
    segments.push(path);
    console.log(`Rendered ${i + 1}/${storyboard.shots.length}: ${shot.id}`);
  }
  const filters = segments.map((_, i) => `[${i}:v]settb=AVTB,setpts=PTS-STARTPTS[v${i}]`);
  let duration = storyboard.shots[0].seconds;
  let prior = "v0";
  for (let i = 1; i < segments.length; i++) {
    const next = `x${i}`;
    filters.push(`[${prior}][v${i}]xfade=transition=fade:duration=${CROSSFADE_SECONDS}:offset=${(duration - CROSSFADE_SECONDS).toFixed(4)}[${next}]`);
    prior = next;
    duration += storyboard.shots[i].seconds - CROSSFADE_SECONDS;
  }
  const video = join(output, `hamsterdan-${storyboard.slug}.mp4`);
  await run(["ffmpeg", "-v", "error", "-y", "-filter_complex_threads", "1", ...segments.flatMap((path) => ["-i", path]),
    "-filter_complex", filters.join(";"), "-map", `[${prior}]`, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
    "-threads", "4", "-pix_fmt", "yuv420p", "-r", "30", "-an", "-movflags", "+faststart", video]);
  const probe = JSON.parse(await run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration,size", "-of", "json", video]));
  if (probe.streams.length !== 1 || probe.streams[0].codec_name !== "h264" || probe.streams[0].width !== FRAME.width || probe.streams[0].height !== FRAME.height || probe.streams[0].r_frame_rate !== "30/1" || Math.abs(Number(probe.format.duration) - duration) > 0.1) {
    throw new Error("Rendered video does not match the planned silent H.264 delivery");
  }
  await run(["ffmpeg", "-v", "error", "-i", video, "-f", "null", "-"]);
  const videoSha256 = sha256(await readFile(video));
  await writeFile(join(output, "render.json"), JSON.stringify({kind: "recovered-proof-demo", manifestSha256, sources: shotFiles, frame: FRAME, captionHeight: CAPTION_HEIGHT,
    shots: storyboard.shots, durationSeconds: duration, probe, video: {file: video, sha256: videoSha256}, fullDecode: "passed"}, null, 2) + "\n");
  await writeFile(join(output, "SHA256SUMS"), `${videoSha256}  hamsterdan-${storyboard.slug}.mp4\n`);
  console.log(video);
};

if (import.meta.main) {
  const [mode] = process.argv.slice(2);
  if (mode !== "stills" && mode !== "render") throw new Error("Usage: bun run live/proof-demo.ts stills|render");
  await renderProofDemo(resolve("live/manifests/pr83-demo.json"), resolve("output/proof/pr83-dark-demo"), mode);
}
