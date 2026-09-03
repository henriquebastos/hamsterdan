import {afterAll, beforeAll, describe, expect, test} from "bun:test";
import {cp, mkdtemp, readFile, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium, type Browser} from "playwright";
import {captureFixtureEvidence} from "./capture";
import {pngDimensions} from "./png";
import {CAPTION_HEIGHT, captionStripHtml, EVIDENCE_PANE, FRAME, renderCaptionStrip, renderTransitions} from "./transition-render";

let browser: Browser;
let seedDirectory: string;

const manifestValue = {
  schema: 1,
  slug: "pr63-v6-hero",
  repository: "HBNetwork/demo-pr-readiness",
  pullRequest: 63,
  expectedState: "closed",
  expectedHead: "ae84a2ae080ef38fdb330ad6317754853d1a0085",
  viewport: {width: 1280, height: 720},
  actors: [{login: "hamster-dan", href: "/apps/hamster-dan"}],
  checkpoints: [
    {
      id: "findings",
      kind: "issue-comment",
      target: "5503038348",
      url: "https://github.com/HBNetwork/demo-pr-readiness/pull/63#issuecomment-5503038348",
      actor: "hamster-dan",
      expectedText: ["Hamsterdan review findings"],
      focusText: "Hamsterdan review findings",
      holdSeconds: 5,
    },
    {
      id: "readiness",
      kind: "issue-comment",
      target: "5503360116",
      url: "https://github.com/HBNetwork/demo-pr-readiness/pull/63#issuecomment-5503360116",
      actor: "hamster-dan",
      expectedText: ["Hamsterdan readiness advisory"],
      focusText: "Hamsterdan readiness advisory",
      holdSeconds: 4,
    },
  ],
};
const manifestBytes = Buffer.from(JSON.stringify(manifestValue));

// A closed pull request: the page is the same on every visit, so consecutive
// stills are pixel-identical and only the anchors tell the two checkpoints
// apart.
const closedPage = `<!doctype html><html><head><title>PR63 - HBNetwork/demo-pr-readiness</title>
<style>body{margin:0;display:flow-root;background:#0d1117;color:#f0f6fc;font:16px system-ui}</style></head><body>
  <header><a href="/HBNetwork/demo-pr-readiness">HBNetwork / demo-pr-readiness</a></header>
  <main>
    <span data-component="StateLabel" data-status="pullClosed">Closed</span>
    <a href="/HBNetwork/demo-pr-readiness/pull/63/commits/ae84a2ae080ef38fdb330ad6317754853d1a0085">ae84a2a</a>
    <div class="timeline-comment-group" id="issuecomment-5503038348">
      <a href="/apps/hamster-dan">hamster-dan bot</a>
      <h2>Hamsterdan review findings</h2>
      <p style="height:200px">Interpret the lease TTL as seconds</p>
    </div>
    <div style="height:2000px;background:#161b22">unrelated conversation</div>
    <div class="timeline-comment-group" id="issuecomment-5503360116">
      <a href="/apps/hamster-dan">hamster-dan bot</a>
      <h2>Hamsterdan readiness advisory</h2>
      <p style="height:200px">Humans keep merge authority</p>
    </div>
  </main>
</body></html>`;

beforeAll(async () => {
  browser = await chromium.launch({headless: true});
  const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-transition-seed-"));
  seedDirectory = (
    await captureFixtureEvidence(manifestBytes, {
      browser,
      outputRoot,
      source: {gitCommit: "6763d5d9fd6850aee9aeac2deed9f4a5d9554be1", clean: true},
      now: new Date("2026-09-02T08:00:00Z"),
      fixture: () => ({status: 200, body: closedPage}),
    })
  ).directory;
});

afterAll(async () => {
  await browser.close();
});

const copySeed = async (): Promise<string> => {
  const root = await mkdtemp(join(tmpdir(), "hamsterdan-transition-"));
  const directory = join(root, "capture");
  await cp(seedDirectory, directory, {recursive: true});
  return directory;
};

const render = (directory: string) =>
  renderTransitions({
    browser,
    manifestBytes,
    captureDirectory: directory,
    outputDirectory: join(directory, "transitions"),
    captureKind: "github-fixture-checkpoint-capture",
    now: new Date("2026-09-02T08:10:00Z"),
  });

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

describe("transition render of a static checkpoint journey", () => {
  test("frames each checkpoint's recorded anchor instead of a meaningless diff", async () => {
    const directory = await copySeed();
    const report = JSON.parse(await readFile(join(directory, "report.json"), "utf8"));
    const [first, second] = report.checkpoints;
    // The two stills are the same closed page, so a pixel diff would give the
    // renderer nothing to frame.
    expect(first.sha256).toBe(second.sha256);
    expect(second.anchor.y).toBeGreaterThan(first.anchor.y + first.anchor.height);

    const rendered = await render(directory);
    expect(rendered.plan).toHaveLength(1);
    expect(rendered.plan[0].framing).toBe("anchor");
    expect(rendered.plan[0].changedPixels).toBe(0);

    const {window} = rendered.plan[0];
    expect(window.height).toBe(EVIDENCE_PANE.height);
    expect(window.y).toBeLessThanOrEqual(second.anchor.y);
    expect(window.y + window.height).toBeGreaterThanOrEqual(second.anchor.y + second.anchor.height);
  }, 120_000);

  test("captions each transition with the manifest's own asserted focus text", async () => {
    const directory = await copySeed();
    const rendered = await render(directory);
    expect(rendered.plan.map(({caption}) => caption)).toEqual(["Hamsterdan readiness advisory"]);
  }, 120_000);

  test("encodes a readable 1:1 camera walk, never a letterboxed full-page sliver", async () => {
    const directory = await copySeed();
    const rendered = await render(directory);
    const probe = JSON.parse(
      await run("ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height:format=duration", "-of", "json", rendered.path),
    ) as {streams: {codec_name: string; width: number; height: number}[]; format: {duration: string}};
    expect(probe.streams).toHaveLength(1);
    expect(probe.streams[0]).toMatchObject({codec_name: "h264", width: FRAME.width, height: FRAME.height});

    const transition = rendered.plan[0];
    const instant = transition.leadSeconds + transition.crossfadeSeconds + transition.holdSeconds / 2;
    const frame = join(directory, "frame.png");
    await run("ffmpeg", "-loglevel", "error", "-y", "-ss", instant.toFixed(3), "-i", rendered.path, "-frames:v", "1", frame);
    const pane = join(directory, "pane.png");
    await run("ffmpeg", "-loglevel", "error", "-y", "-i", frame, "-vf", `crop=${EVIDENCE_PANE.width}:${EVIDENCE_PANE.height}:0:0`, "-frames:v", "1", pane);

    const still = join(directory, "checkpoints", "readiness.png");
    const expected = join(directory, "expected.png");
    const {window} = transition;
    await run(
      "ffmpeg",
      "-loglevel",
      "error",
      "-y",
      "-i",
      still,
      "-vf",
      `crop=${window.width}:${window.height}:${window.x}:${window.y},format=yuv420p`,
      "-frames:v",
      "1",
      expected,
    );
    const comparison = await run("ffmpeg", "-i", expected, "-i", pane, "-lavfi", "psnr", "-f", "null", "-");
    expect(Number(comparison.match(/average:([0-9.]+)/)?.[1])).toBeGreaterThan(30);
  }, 120_000);

  test("walks the page when the archived capture predates anchor boxes", async () => {
    const directory = await copySeed();
    const reportPath = join(directory, "report.json");
    const report = JSON.parse(await readFile(reportPath, "utf8"));
    for (const checkpoint of report.checkpoints) delete checkpoint.anchor;
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);

    const rendered = await render(directory);
    expect(rendered.plan[0].framing).toBe("page-walk");
    expect(rendered.plan[0].window.height).toBe(EVIDENCE_PANE.height);
  }, 120_000);

  test("rejects a still whose pixels no longer match the report", async () => {
    const directory = await copySeed();
    await writeFile(join(directory, "checkpoints", "findings.png"), "tampered");
    await expect(render(directory)).rejects.toThrow(/hash does not match/);
  });

  test("rejects manifest bytes the capture report does not identify", async () => {
    const directory = await copySeed();
    await expect(
      renderTransitions({
        browser,
        manifestBytes: Buffer.concat([manifestBytes, Buffer.from("\n")]),
        captureDirectory: directory,
        outputDirectory: join(directory, "transitions"),
        captureKind: "github-fixture-checkpoint-capture",
        now: new Date("2026-09-02T08:10:00Z"),
      }),
    ).rejects.toThrow(/manifest bytes/);
  });

  test("rejects a live-provenance render of a fixture capture", async () => {
    const directory = await copySeed();
    await expect(
      renderTransitions({
        browser,
        manifestBytes,
        captureDirectory: directory,
        outputDirectory: join(directory, "transitions"),
        captureKind: "github-live-checkpoint-capture",
        now: new Date("2026-09-02T08:10:00Z"),
      }),
    ).rejects.toThrow(/pending live capture/);
  });
});

describe("caption strip", () => {
  test("renders exactly one strip of authored pixels below the evidence pane", async () => {
    const png = await renderCaptionStrip(browser, "Hamsterdan readiness advisory");
    expect(pngDimensions(png)).toEqual({width: FRAME.width, height: CAPTION_HEIGHT});
    expect(CAPTION_HEIGHT + EVIDENCE_PANE.height).toBe(FRAME.height);
  });

  test("escapes caption text instead of letting it become markup", () => {
    const html = captionStripHtml('<script>alert("x")</script>');
    expect(html).not.toContain("<script>alert");
    expect(html).toContain("&#60;script&#62;");
  });
});
