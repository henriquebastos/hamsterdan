import {afterAll, beforeAll, describe, expect, test} from "bun:test";
import {mkdtemp, readdir, readFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium, type Browser} from "playwright";
import {parseManifest} from "./manifest";
import {pngDimensions} from "./png";
import {EVIDENCE_PANE, FRAME, renderTransitions} from "./transition-render";
import {parseWatchOverrides} from "./watch-cli";
import {resolveWatchPlan, stateId, watchFixtureStates} from "./watch";

const rejection = async (promise: Promise<unknown>): Promise<Error> => {
  const outcome = await promise.then(
    () => undefined,
    (error: unknown) => error,
  );
  if (!(outcome instanceof Error)) throw new Error("expected the watch to reject");
  return outcome;
};

let browser: Browser;

beforeAll(async () => {
  browser = await chromium.launch({headless: true});
});

afterAll(async () => {
  await browser.close();
});

const WATCHED_URL = "https://github.com/HBNetwork/demo-pr-readiness/pull/61";

const manifestValue = {
  schema: 1,
  slug: "pr61-v5-hero",
  repository: "HBNetwork/demo-pr-readiness",
  pullRequest: 61,
  expectedState: "open",
  expectedHead: "e3d11a8171dbbb4af910b7c199a5f240dfb2441e",
  viewport: {width: 1280, height: 720},
  actors: [
    {login: "henriquebastos", href: "/henriquebastos"},
    {login: "hamster-dan", href: "/apps/hamster-dan"},
  ],
  checkpoints: [
    {
      id: "findings",
      kind: "issue-comment",
      target: "5312507139",
      url: "https://github.com/HBNetwork/demo-pr-readiness/pull/61#issuecomment-5312507139",
      actor: "hamster-dan",
      expectedText: ["Hamsterdan review findings"],
      focusText: "Hamsterdan review findings",
      holdSeconds: 2,
    },
  ],
  watch: {pollSeconds: 1, durationSeconds: 60, maxStates: 4, caption: "PR 61 live journey"},
};
const manifestBytes = Buffer.from(JSON.stringify(manifestValue));

const source = {gitCommit: "6763d5d9fd6850aee9aeac2deed9f4a5d9554be1", clean: true as const};

// A pull-request page that gains one visible event per load: a review comment,
// a board edit, then a check flip. Each event appends content, so consecutive
// stills differ exactly where the new content landed.
const EVENTS = [
  "",
  `<div class="timeline-comment-group" id="issuecomment-5312507139">
     <a href="/apps/hamster-dan">hamster-dan bot</a>
     <h2>Hamsterdan review findings</h2>
     <p style="height:160px">Calculate lease duration in seconds</p>
   </div>`,
  `<div class="timeline-comment-group" id="issuecomment-5312507140">
     <a href="/apps/hamster-dan">hamster-dan bot</a>
     <h2>Hamsterdan decision board</h2>
     <p style="height:160px">checks: pending &middot; review: waiting</p>
   </div>`,
  `<div class="timeline-comment-group" id="issuecomment-5312507141">
     <a href="/henriquebastos">henriquebastos</a>
     <h2>All checks have passed</h2>
     <p style="height:160px">checks: success &middot; review: clear</p>
   </div>`,
];

const journeyPage = (upTo: number): string => `<!doctype html>
<html><head><title>Hamsterdan demo - Pull Request #61 - HBNetwork/demo-pr-readiness</title>
<style>body{margin:0;display:flow-root;background:#0d1117;color:#f0f6fc;font:16px system-ui}
h2{margin:8px 0}p{margin:0}</style></head>
<body>
  <header><a href="/HBNetwork/demo-pr-readiness">HBNetwork / demo-pr-readiness</a></header>
  <main>
    <span data-component="StateLabel" data-status="pullOpened">Open</span>
    <a href="/HBNetwork/demo-pr-readiness/pull/61/commits/e3d11a8171dbbb4af910b7c199a5f240dfb2441e">e3d11a8</a>
    <p><a href="/henriquebastos">henriquebastos</a> opened this pull request</p>
    <div style="height:800px;background:#161b22">Pull request description</div>
    ${EVENTS.slice(0, upTo + 1).join("\n")}
  </main>
</body></html>`;

// One request advances the journey by one event, so the watch observes a
// deterministic sequence instead of racing a wall clock.
const journeyFixture = () => {
  let served = -1;
  return () => {
    served = Math.min(served + 1, EVENTS.length - 1);
    return {status: 200, body: journeyPage(served)};
  };
};

const watch = async (fixture: () => {status: number; body: string}, overrides = {}) => {
  const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-watch-"));
  const result = await watchFixtureStates(manifestBytes, {
    browser,
    outputRoot,
    source,
    now: new Date("2026-09-02T08:00:00Z"),
    fixture,
    ...overrides,
  });
  return {outputRoot, ...result};
};

describe("watched state-sequence capture", () => {
  test("records the ordered sequence of page states with verified full-page stills", async () => {
    const result = await watch(journeyFixture());
    const states = result.report.checkpoints;

    expect(result.report.kind).toBe("github-fixture-state-sequence-capture");
    expect(states.map(({id}) => id)).toEqual(["state-001", "state-002", "state-003", "state-004"]);
    expect(states.map(({target}) => target)).toEqual(["1", "2", "3", "4"]);
    expect(states.map(({kind}) => kind)).toEqual(["state", "state", "state", "state"]);

    for (const [index, state] of states.entries()) {
      const bytes = await readFile(join(result.directory, state.file));
      expect(pngDimensions(bytes)).toEqual(state.dimensions);
      expect(state.dimensions.height).toBe(state.capture.scrollHeight);
      expect(state.dimensions.height).toBeGreaterThan(720);
      expect(state.capture.fullPage).toBeTrue();
      if (index > 0) {
        // The journey only ever appends, so each state is taller and later.
        expect(state.dimensions.height).toBeGreaterThan(states[index - 1].dimensions.height);
        expect(Date.parse(state.capturedAt)).toBeGreaterThanOrEqual(Date.parse(states[index - 1].capturedAt));
      }
    }
    expect((await readdir(join(result.directory, "dom"))).sort()).toEqual(
      states.flatMap(({id}) => [`${id}.after.html`, `${id}.before.html`]).sort(),
    );
  }, 60_000);

  test("records nothing new while the watched page content stays the same", async () => {
    // A page that never changes must not become four identical states.
    const error = await rejection(watch(() => ({status: 200, body: journeyPage(1)}), {durationSeconds: 4}));
    expect(error.message).toMatch(/observed 1 state/);
  }, 60_000);

  test("fails closed and publishes nothing when the watched page loses its identity", async () => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-watch-closed-"));
    const error = await rejection(
      watchFixtureStates(manifestBytes, {
        browser,
        outputRoot,
        source,
        now: new Date("2026-09-02T08:00:00Z"),
        fixture: () => ({status: 200, body: "<html><body><main>Verify your identity</main></body></html>"}),
      }),
    );
    expect(error.message).toMatch(/without authentication/);
    expect(await readdir(outputRoot)).toEqual([]);
  }, 60_000);

  test("fails closed when the watched pull request is not in the declared state", async () => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-watch-state-"));
    const error = await rejection(
      watchFixtureStates(manifestBytes, {
        browser,
        outputRoot,
        source,
        now: new Date("2026-09-02T08:00:00Z"),
        fixture: () => ({status: 200, body: journeyPage(1).replace("pullOpened", "pullMerged")}),
      }),
    );
    expect(error.message).toMatch(/does not show a open pull request/);
    expect(await readdir(outputRoot)).toEqual([]);
  }, 60_000);

  test("numbers states monotonically from one", () => {
    expect([1, 2, 10].map(stateId)).toEqual(["state-001", "state-002", "state-010"]);
  });
});

describe("watch cadence and duration", () => {
  const manifest = parseManifest(manifestValue);

  test("takes the cadence and duration from the manifest", () => {
    expect(resolveWatchPlan(manifest, {})).toEqual(manifestValue.watch);
  });

  test("lets a CLI flag override either of them", () => {
    expect(parseWatchOverrides(["--poll-seconds=5", "--duration-seconds=120"])).toEqual({
      pollSeconds: 5,
      durationSeconds: 120,
    });
    const plan = resolveWatchPlan(manifest, {pollSeconds: 5, durationSeconds: 120});
    expect(plan.pollSeconds).toBe(5);
    expect(plan.durationSeconds).toBe(120);
    expect(plan.caption).toBe(manifestValue.watch.caption);
  });

  test("rejects an unknown flag and an out-of-range cadence", () => {
    expect(() => parseWatchOverrides(["--selector=body"])).toThrow(/unknown watch flag/);
    expect(() => resolveWatchPlan(manifest, {pollSeconds: 600})).toThrow(/poll cadence/);
    expect(() => resolveWatchPlan(manifest, {pollSeconds: 30, durationSeconds: 10})).toThrow(/fit inside/);
  });

  test("refuses to watch a manifest that declares no watch plan", () => {
    const {watch: _watch, ...withoutWatch} = manifestValue;
    expect(() => resolveWatchPlan(parseManifest(withoutWatch), {})).toThrow(/no watch plan/);
  });
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

describe("transition render of a watched journey", () => {
  test("shows every change at 1:1 as one transition per consecutive state pair", async () => {
    const captured = await watch(journeyFixture());
    const outputDirectory = join(captured.directory, "transitions");
    const rendered = await renderTransitions({
      browser,
      manifestBytes,
      captureDirectory: captured.directory,
      outputDirectory,
      captureKind: "github-fixture-state-sequence-capture",
      now: new Date("2026-09-02T08:10:00Z"),
    });

    expect(rendered.plan).toHaveLength(captured.report.checkpoints.length - 1);
    expect(rendered.plan.map(({framing}) => framing)).toEqual(["changed-region", "changed-region", "changed-region"]);
    expect(rendered.report.video.width).toBe(FRAME.width);
    expect(rendered.report.video.height).toBe(FRAME.height);
    expect(rendered.report.video.audioStreams).toBe(0);
    expect(rendered.report.transitions.map(({caption}) => caption)).toEqual([
      "PR 61 live journey — state 2",
      "PR 61 live journey — state 3",
      "PR 61 live journey — state 4",
    ]);

    const probe = JSON.parse(
      await run(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate:format=duration",
        "-of",
        "json",
        rendered.path,
      ),
    ) as {streams: {codec_name: string; width: number; height: number}[]; format: {duration: string}};
    expect(probe.streams).toHaveLength(1);
    expect(probe.streams[0].codec_name).toBe("h264");
    expect(probe.streams[0].width).toBe(FRAME.width);
    expect(probe.streams[0].height).toBe(FRAME.height);

    // Each transition's arriving hold must be the real still, cropped to the
    // changed region at 1:1 — not a scaled-down whole page.
    let elapsed = 0;
    for (const transition of rendered.plan) {
      const holdInstant = elapsed + transition.leadSeconds + transition.crossfadeSeconds + transition.holdSeconds / 2;
      elapsed += transition.leadSeconds + transition.crossfadeSeconds + transition.holdSeconds;

      const frame = join(captured.outputRoot, `frame-${transition.index}.png`);
      await run("ffmpeg", "-loglevel", "error", "-y", "-ss", holdInstant.toFixed(3), "-i", rendered.path, "-frames:v", "1", frame);
      const pane = join(captured.outputRoot, `pane-${transition.index}.png`);
      await run("ffmpeg", "-loglevel", "error", "-y", "-i", frame, "-vf", `crop=${EVIDENCE_PANE.width}:${EVIDENCE_PANE.height}:0:0`, "-frames:v", "1", pane);

      const arriving = join(captured.directory, captured.report.checkpoints[transition.index + 1].file);
      const {window} = transition;
      const expectedPane = join(captured.outputRoot, `expected-${transition.index}.png`);
      await run(
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-i",
        arriving,
        "-vf",
        `pad=${Math.max(transition.canvas.width, EVIDENCE_PANE.width)}:${Math.max(transition.canvas.height, EVIDENCE_PANE.height)}:0:0:black,crop=${window.width}:${window.height}:${window.x}:${window.y},format=yuv420p`,
        "-frames:v",
        "1",
        expectedPane,
      );
      const comparison = await run("ffmpeg", "-i", expectedPane, "-i", pane, "-lavfi", "psnr", "-f", "null", "-");
      expect(Number(comparison.match(/average:([0-9.]+)/)?.[1])).toBeGreaterThan(30);
    }
  }, 180_000);
});
