import {mkdir, readFile} from "node:fs/promises";
import {dirname, isAbsolute, relative, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {chromium} from "playwright";
import {parseManifest} from "./manifest";
import {watchPublicStates} from "./watch";

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

export const parseWatchOverrides = (argv: readonly string[]): {pollSeconds?: number; durationSeconds?: number} => {
  const overrides: {pollSeconds?: number; durationSeconds?: number} = {};
  for (const argument of argv) {
    const match = /^--(poll-seconds|duration-seconds)=([1-9][0-9]{0,3})$/.exec(argument);
    if (!match) throw new Error(`unknown watch flag ${argument}`);
    if (match[1] === "poll-seconds") overrides.pollSeconds = Number(match[2]);
    else overrides.durationSeconds = Number(match[2]);
  }
  return overrides;
};

const main = async (): Promise<void> => {
  const liveRoot = dirname(fileURLToPath(import.meta.url));
  const toolRoot = resolve(liveRoot, "..");
  const repositoryRoot = resolve(toolRoot, "../..");
  const manifestRoot = resolve(liveRoot, "manifests");
  const manifestArgument = process.argv[2];
  if (!manifestArgument) throw new Error("usage: watch-cli.ts <live manifest> [--poll-seconds=N] [--duration-seconds=N]");
  const manifestPath = resolve(process.cwd(), manifestArgument);
  const manifestRelative = relative(manifestRoot, manifestPath);
  if (isAbsolute(manifestRelative) || manifestRelative.startsWith("..") || !manifestRelative.endsWith(".json")) {
    throw new Error("live manifest must be a checked-in file under live/manifests");
  }
  const overrides = parseWatchOverrides(process.argv.slice(3));

  const status = await runGit(repositoryRoot, "status", "--porcelain=v1", "--untracked-files=all");
  if (status !== "") throw new Error("live acceptance capture requires a clean committed worktree");
  const gitCommit = await runGit(repositoryRoot, "rev-parse", "HEAD");
  const manifestBytes = await readFile(manifestPath);
  const manifest = parseManifest(JSON.parse(manifestBytes.toString("utf8")));
  const outputRoot = resolve(toolRoot, "output", "live", `${manifest.slug}-states`);
  await mkdir(outputRoot, {recursive: true});

  const browser = await chromium.launch({headless: true});
  try {
    const result = await watchPublicStates(manifestBytes, {
      browser,
      outputRoot,
      source: {gitCommit, clean: true},
      now: new Date(),
      ...overrides,
    });
    console.log(result.directory);
  } finally {
    await browser.close();
  }
};

if (import.meta.main) await main();
