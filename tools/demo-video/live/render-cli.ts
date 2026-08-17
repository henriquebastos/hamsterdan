import {readFile} from "node:fs/promises";
import {dirname, isAbsolute, relative, resolve, sep} from "node:path";
import {fileURLToPath} from "node:url";
import {parseManifest} from "./manifest";
import {renderEvidence} from "./render";

const liveRoot = dirname(fileURLToPath(import.meta.url));
const toolRoot = resolve(liveRoot, "..");
const manifestRoot = resolve(liveRoot, "manifests");

export const requireCaptureRunDirectory = (captureRoot: string, captureDirectory: string): void => {
  const path = relative(captureRoot, captureDirectory);
  if (path === "" || isAbsolute(path) || path === ".." || path.startsWith(`..${sep}`) || dirname(path) !== ".") {
    throw new Error("capture directory must be one run directly under the manifest output root");
  }
};

const main = async (): Promise<void> => {
  const manifestArgument = process.argv[2];
  const captureArgument = process.argv[3];
  if (!manifestArgument || !captureArgument) {
    throw new Error("usage: render-cli.ts <live manifest> <capture directory>");
  }
  const manifestPath = resolve(process.cwd(), manifestArgument);
  const manifestRelative = relative(manifestRoot, manifestPath);
  if (isAbsolute(manifestRelative) || manifestRelative.startsWith("..") || !manifestRelative.endsWith(".json")) {
    throw new Error("live manifest must be a checked-in file under live/manifests");
  }
  const manifestBytes = await readFile(manifestPath);
  const manifest = parseManifest(JSON.parse(manifestBytes.toString("utf8")));
  const captureRoot = resolve(toolRoot, "output", "live", manifest.slug);
  const captureDirectory = resolve(process.cwd(), captureArgument);
  requireCaptureRunDirectory(captureRoot, captureDirectory);

  const result = await renderEvidence(manifestBytes, captureDirectory, new Date());
  console.log(result.path);
};

if (import.meta.main) await main();
