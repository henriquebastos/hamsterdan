import {mkdir, readFile} from "node:fs/promises";
import {dirname, isAbsolute, relative, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {chromium} from "playwright";
import {capturePublicEvidence} from "./capture";
import {parseManifest} from "./manifest";

const runGit = async (root: string, ...arguments_: string[]): Promise<string> => {
  const child = Bun.spawn(["git", "-C", root, ...arguments_], {stdout: "pipe", stderr: "pipe"});
  const [stdout, stderr, exit] = await Promise.all([
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
    child.exited,
  ]);
  if (exit !== 0) throw new Error(`git ${arguments_.join(" ")} failed: ${stderr.trim()}`);
  return stdout.trim();
};

const liveRoot = dirname(fileURLToPath(import.meta.url));
const toolRoot = resolve(liveRoot, "..");
const repositoryRoot = resolve(toolRoot, "../..");
const manifestRoot = resolve(liveRoot, "manifests");
const manifestArgument = process.argv[2];
if (!manifestArgument) throw new Error("usage: capture-cli.ts <live manifest>");
const manifestPath = resolve(process.cwd(), manifestArgument);
const manifestRelative = relative(manifestRoot, manifestPath);
if (isAbsolute(manifestRelative) || manifestRelative.startsWith("..") || !manifestRelative.endsWith(".json")) {
  throw new Error("live manifest must be a checked-in file under live/manifests");
}

const status = await runGit(repositoryRoot, "status", "--porcelain=v1", "--untracked-files=all");
if (status !== "") throw new Error("live acceptance capture requires a clean committed worktree");
const gitCommit = await runGit(repositoryRoot, "rev-parse", "HEAD");
const manifestBytes = await readFile(manifestPath);
const manifest = parseManifest(JSON.parse(manifestBytes.toString("utf8")));
const outputRoot = resolve(toolRoot, "output", "live", manifest.slug);
await mkdir(outputRoot, {recursive: true});

const browser = await chromium.launch({headless: true});
try {
  const result = await capturePublicEvidence(manifestBytes, {
    browser,
    outputRoot,
    source: {gitCommit, clean: true},
    now: new Date(),
  });
  console.log(result.directory);
} finally {
  await browser.close();
}
