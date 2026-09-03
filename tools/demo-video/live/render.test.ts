import {afterAll, beforeAll, describe, expect, test} from "bun:test";
import {createHash} from "node:crypto";
import {cp, mkdtemp, readdir, readFile, rename, rm, symlink, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium, type Browser} from "playwright";
import {captureFixtureEvidence} from "./capture";
import {parseManifest, type CaptureManifest} from "./manifest";
import {requireCaptureRunDirectory} from "./render-cli";
import {renderEvidence, renderFixtureEvidence} from "./render";

let browser: Browser;
let seedDirectory: string;

const manifestValue = {
  schema: 1,
  slug: "pr61-v5-hero",
  repository: "HBNetwork/demo-pr-readiness",
  pullRequest: 61,
  expectedState: "open",
  expectedHead: "e3d11a8171dbbb4af910b7c199a5f240dfb2441e",
  viewport: {width: 1280, height: 720},
  actors: [{login: "hamster-dan", href: "/apps/hamster-dan"}],
  checkpoints: [
    {
      id: "findings-top",
      kind: "issue-comment",
      target: "5312507139",
      url: "https://github.com/HBNetwork/demo-pr-readiness/pull/61#issuecomment-5312507139",
      actor: "hamster-dan",
      expectedText: ["Hamsterdan review findings", "Calculate lease duration in seconds"],
      focusText: "Hamsterdan review findings",
      holdSeconds: 2,
    },
    {
      id: "findings-bottom",
      kind: "issue-comment",
      target: "5312507139",
      url: "https://github.com/HBNetwork/demo-pr-readiness/pull/61#issuecomment-5312507139",
      actor: "hamster-dan",
      expectedText: ["Hamsterdan review findings", "Calculate lease duration in seconds"],
      focusText: "Calculate lease duration in seconds",
      holdSeconds: 2,
    },
  ],
};
const manifestBytes = Buffer.from(JSON.stringify(manifestValue));
const manifest: CaptureManifest = parseManifest(manifestValue);
const FIT_FILTER =
  `scale=${manifest.viewport.width}:${manifest.viewport.height}:force_original_aspect_ratio=decrease,` +
  `pad=${manifest.viewport.width}:${manifest.viewport.height}:(ow-iw)/2:(oh-ih)/2:color=black`;

const fixtureHtml = `<!doctype html><html><head><title>PR61 · HBNetwork/demo-pr-readiness</title>
  <style>body{margin:0;display:flow-root}</style></head><body>
  <header><a href="/HBNetwork/demo-pr-readiness">HBNetwork / demo-pr-readiness</a></header>
  <main>
    <span data-component="StateLabel" data-status="pullOpened">Open</span>
    <a href="/HBNetwork/demo-pr-readiness/pull/61/commits/e3d11a8171dbbb4af910b7c199a5f240dfb2441e">e3d11a8</a>
    <div class="timeline-comment-group" id="issuecomment-5312507139">
      <a href="/apps/hamster-dan">hamster-dan bot</a>
      <h2>Hamsterdan review findings</h2>
      <div style="height: 1000px; background: #123456"></div>
      <p>Calculate lease duration in seconds</p>
    </div>
  </main>
</body></html>`;

beforeAll(async () => {
  browser = await chromium.launch({headless: true});
  const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-render-seed-"));
  seedDirectory = (
    await captureFixtureEvidence(manifestBytes, {
      browser,
      outputRoot,
      source: {
        gitCommit: "6763d5d9fd6850aee9aeac2deed9f4a5d9554be1",
        clean: true,
      },
      now: new Date("2026-08-17T08:00:00Z"),
      fixture: () => ({status: 200, body: fixtureHtml}),
    })
  ).directory;
});

afterAll(async () => {
  await browser.close();
});

const copySeed = async (): Promise<string> => {
  const root = await mkdtemp(join(tmpdir(), "hamsterdan-live-render-"));
  const directory = join(root, "capture");
  await cp(seedDirectory, directory, {recursive: true});
  return directory;
};

const run = async (...args: string[]): Promise<string> => {
  const child = Bun.spawn(args, {stdout: "pipe", stderr: "pipe"});
  const [stdout, stderr, exit] = await Promise.all([
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
    child.exited,
  ]);
  if (exit !== 0) throw new Error(`${args.join(" ")} failed: ${stderr}`);
  return `${stdout}\n${stderr}`;
};

describe("verified checkpoint montage", () => {
  test("renders only ordered hash-verified screenshots as silent H.264", async () => {
    const directory = await copySeed();
    const result = await renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"));
    expect(result.video.codec).toBe("h264");
    expect(result.video.audioStreams).toBe(0);
    expect(result.video.durationSeconds).toBeCloseTo(4, 1);

    const report = JSON.parse(await readFile(join(directory, "report.json"), "utf8"));
    expect(report.kind).toBe("github-fixture-checkpoint-capture");
    expect(report.video.file).toBe("hamsterdan-pr61-v5-hero-fixture-checkpoints.mp4");
    expect(report.video.sha256).toBe(result.video.sha256);
    expect(await readFile(join(directory, "SHA256SUMS"), "utf8")).toContain(result.video.sha256);

    for (const [index, second] of [1, 3].entries()) {
      const decoded = join(directory, `decoded-${index}.png`);
      await run("ffmpeg", "-loglevel", "error", "-ss", String(second), "-i", result.path, "-frames:v", "1", decoded);
      // Each still is full-page and therefore taller than the montage canvas;
      // the frame must be that whole still fitted in, never a crop of it.
      const fitted = join(directory, `fitted-${index}.png`);
      await run(
        "ffmpeg",
        "-loglevel",
        "error",
        "-i",
        join(directory, report.checkpoints[index].file),
        "-vf",
        `${FIT_FILTER},format=yuv420p`,
        "-frames:v",
        "1",
        fitted,
      );
      const comparison = await run("ffmpeg", "-i", fitted, "-i", decoded, "-lavfi", "psnr", "-f", "null", "-");
      const average = Number(comparison.match(/average:([0-9.]+)/)?.[1]);
      expect(average).toBeGreaterThan(30);
    }
    expect((await readdir(directory, {recursive: true})).filter((name) => name.endsWith(".pdf"))).toEqual([]);
  }, 30_000);

  test("rejects a still whose recorded height stops matching its scrollHeight", async () => {
    const directory = await copySeed();
    const reportPath = join(directory, "report.json");
    const report = JSON.parse(await readFile(reportPath, "utf8"));
    report.checkpoints[0].capture.scrollHeight = report.checkpoints[0].dimensions.height - 1;
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(
      /cropped/,
    );
  });

  test("rejects a still whose pixels were cropped after the report was written", async () => {
    const directory = await copySeed();
    const still = join(directory, "checkpoints", "findings-top.png");
    const cropped = join(directory, "cropped.png");
    await run("ffmpeg", "-loglevel", "error", "-i", still, "-vf", "crop=1280:720:0:0", cropped);
    const bytes = await readFile(cropped);
    await rm(cropped);
    await writeFile(still, bytes);

    const reportPath = join(directory, "report.json");
    const report = JSON.parse(await readFile(reportPath, "utf8"));
    report.checkpoints[0].sha256 = createHash("sha256").update(bytes).digest("hex");
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(
      /cropped/,
    );
  }, 30_000);

  test("rejects an unreported DOM input", async () => {
    const directory = await copySeed();
    await cp(join(directory, "dom/findings-top.before.html"), join(directory, "dom/extra.before.html"));
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(
      /unreported HTML/,
    );
  });

  test("rejects a tampered checkpoint DOM", async () => {
    const directory = await copySeed();
    await writeFile(join(directory, "dom/findings-top.after.html"), "<html>rewritten</html>");
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(
      /after DOM does not match/,
    );
  });

  test("checksums the before and after DOM alongside every still", async () => {
    const directory = await copySeed();
    await renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"));
    const sums = await readFile(join(directory, "SHA256SUMS"), "utf8");
    for (const line of ["dom/findings-top.before.html", "dom/findings-top.after.html", "checkpoints/findings-top.png"]) {
      expect(sums).toContain(line);
    }
  }, 30_000);

  test("rejects a hash-mismatched screenshot without changing the report", async () => {
    const directory = await copySeed();
    const reportPath = join(directory, "report.json");
    const before = await readFile(reportPath, "utf8");
    await writeFile(join(directory, "checkpoints/findings-top.png"), "tampered");
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(/hash/);
    expect(await readFile(reportPath, "utf8")).toBe(before);
  });

  test("rejects reordered report inputs", async () => {
    const directory = await copySeed();
    const reportPath = join(directory, "report.json");
    const report = JSON.parse(await readFile(reportPath, "utf8"));
    report.checkpoints.reverse();
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(/order/);
  });

  test("rejects unreported PNG inputs", async () => {
    const directory = await copySeed();
    await cp(join(directory, "checkpoints/findings-top.png"), join(directory, "checkpoints/extra.png"));
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(/unreported/);
  });

  test("rejects fixture provenance even when every checkpoint is valid", async () => {
    const directory = await copySeed();
    await expect(renderEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(/pending live capture/);
  });

  test("binds the report to the exact manifest bytes", async () => {
    const directory = await copySeed();
    const equivalentManifestBytes = Buffer.concat([manifestBytes, Buffer.from("\n")]);
    await expect(renderFixtureEvidence(equivalentManifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(
      /manifest bytes/,
    );
  });

  test("snapshots caller-owned manifest bytes before filesystem awaits", async () => {
    const directory = await copySeed();
    const changed = manifestBytes.toString("utf8").replace('"holdSeconds":2', '"holdSeconds":3');
    const mutableBytes = Buffer.from(changed);
    expect(mutableBytes.byteLength).toBe(manifestBytes.byteLength);
    const rendering = renderFixtureEvidence(mutableBytes, directory, new Date("2026-08-17T08:05:00Z"));
    mutableBytes.set(manifestBytes);
    await expect(rendering).rejects.toThrow(/manifest bytes/);
  });

  test("rejects a report path escape before opening an input", async () => {
    const directory = await copySeed();
    const reportPath = join(directory, "report.json");
    const report = JSON.parse(await readFile(reportPath, "utf8"));
    report.checkpoints[0].file = "../escape.png";
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(/checkpoint file/);
  });

  test("rejects symlinked report and checkpoint inputs", async () => {
    const reportDirectory = await copySeed();
    await rename(join(reportDirectory, "report.json"), join(reportDirectory, "report-real.json"));
    await symlink("report-real.json", join(reportDirectory, "report.json"));
    await expect(renderFixtureEvidence(manifestBytes, reportDirectory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(/symlink/);

    const checkpointDirectory = await copySeed();
    const checkpoint = join(checkpointDirectory, "checkpoints", "findings-top.png");
    await rename(checkpoint, `${checkpoint}.real`);
    await symlink("findings-top.png.real", checkpoint);
    await expect(renderFixtureEvidence(manifestBytes, checkpointDirectory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(/symlink/);
  });

  test("rejects a preexisting symlink at the video output path", async () => {
    const directory = await copySeed();
    await writeFile(join(directory, "outside.mp4"), "not a video");
    await symlink("outside.mp4", join(directory, "hamsterdan-pr61-v5-hero-fixture-checkpoints.mp4"));
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(
      /video path.*symlink/,
    );
  });

  test("rejects an unknown report field", async () => {
    const directory = await copySeed();
    const reportPath = join(directory, "report.json");
    const report = JSON.parse(await readFile(reportPath, "utf8"));
    report.cookies = [];
    const temporary = `${reportPath}.new`;
    await writeFile(temporary, `${JSON.stringify(report, null, 2)}\n`);
    await rename(temporary, reportPath);
    await expect(renderFixtureEvidence(manifestBytes, directory, new Date("2026-08-17T08:05:00Z"))).rejects.toThrow(/report/);
  });
});

describe("render CLI capture-directory boundary", () => {
  const root = join("/tmp", "hamsterdan", "output", "live", "pr61-v5-hero");

  test("accepts exactly one named run below the manifest output root", () => {
    expect(() => requireCaptureRunDirectory(root, join(root, "20260817T100000Z-81514a915248"))).not.toThrow();
  });

  test("rejects the manifest output root itself and nested descendants", () => {
    expect(() => requireCaptureRunDirectory(root, root)).toThrow(/directly under/);
    expect(() => requireCaptureRunDirectory(root, join(root, "run", "nested"))).toThrow(/directly under/);
  });
});
