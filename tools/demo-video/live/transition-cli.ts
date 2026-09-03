import {readFile} from "node:fs/promises";
import {dirname, isAbsolute, join, relative, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {chromium} from "playwright";
import {parseManifest} from "./manifest";
import {requireCaptureRunDirectory} from "./render-cli";
import {renderTransitions} from "./transition-render";
import type {CaptureReportKind} from "./render";

const main = async (): Promise<void> => {
  const liveRoot = dirname(fileURLToPath(import.meta.url));
  const toolRoot = resolve(liveRoot, "..");
  const manifestRoot = resolve(liveRoot, "manifests");
  const manifestArgument = process.argv[2];
  const captureArgument = process.argv[3];
  const flags = process.argv.slice(4);
  if (!manifestArgument || !captureArgument) {
    throw new Error("usage: transition-cli.ts <live manifest> <capture directory> [--states]");
  }
  for (const flag of flags) {
    if (flag !== "--states") throw new Error(`unknown transition flag ${flag}`);
  }
  const watched = flags.includes("--states");

  const manifestPath = resolve(process.cwd(), manifestArgument);
  const manifestRelative = relative(manifestRoot, manifestPath);
  if (isAbsolute(manifestRelative) || manifestRelative.startsWith("..") || !manifestRelative.endsWith(".json")) {
    throw new Error("live manifest must be a checked-in file under live/manifests");
  }
  const manifestBytes = await readFile(manifestPath);
  const manifest = parseManifest(JSON.parse(manifestBytes.toString("utf8")));
  const captureRoot = resolve(toolRoot, "output", "live", watched ? `${manifest.slug}-states` : manifest.slug);
  const captureDirectory = resolve(process.cwd(), captureArgument);
  requireCaptureRunDirectory(captureRoot, captureDirectory);

  const captureKind: CaptureReportKind = watched
    ? "github-live-state-sequence-capture"
    : "github-live-checkpoint-capture";
  const browser = await chromium.launch({headless: true});
  try {
    const result = await renderTransitions({
      browser,
      manifestBytes,
      captureDirectory,
      outputDirectory: join(captureDirectory, "transitions"),
      captureKind,
      now: new Date(),
    });
    console.log(result.path);
  } finally {
    await browser.close();
  }
};

if (import.meta.main) await main();
