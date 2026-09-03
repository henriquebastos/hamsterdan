import {afterAll, beforeAll, describe, expect, test} from "bun:test";
import {createHash} from "node:crypto";
import {mkdtemp, readdir, readFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium, type Browser} from "playwright";
import {captureFixtureEvidence, type FixtureResponse} from "./capture";
import {parseManifest, type CaptureManifest} from "./manifest";
import {pngDimensions} from "./png";

// bun:test only settles `expect(pendingPromise).rejects` on a slow tick, which
// starves Playwright's transport at about one second per round trip and blows
// the default test timeout. Settle the capture first, then assert on the error.
const rejection = async (promise: Promise<unknown>): Promise<Error> => {
  const outcome = await promise.then(
    () => undefined,
    (error: unknown) => error,
  );
  if (!(outcome instanceof Error)) {
    throw new Error("expected the capture to reject");
  }
  return outcome;
};

let browser: Browser;

beforeAll(async () => {
  browser = await chromium.launch({headless: true});
});

afterAll(async () => {
  await browser.close();
});

const manifest = (): CaptureManifest =>
  parseManifest({
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
        id: "findings",
        kind: "issue-comment",
        target: "5312507139",
        url: "https://github.com/HBNetwork/demo-pr-readiness/pull/61#issuecomment-5312507139",
        actor: "hamster-dan",
        expectedText: ["Hamsterdan review findings", "Calculate lease duration in seconds"],
        focusText: "Hamsterdan review findings",
        holdSeconds: 2,
      },
    ],
  });

const pageHtml = ({
  hidden = false,
  duplicate = false,
  dashboard = false,
  script = "",
  style = "body{margin:0;display:flow-root}",
  stateStatus = "pullOpened",
} = {}) => `<!doctype html>
<html><head><title>Hamsterdan demo · Pull Request #61 · HBNetwork/demo-pr-readiness</title><style>${style}</style></head>
<body>
  <header><a href="/HBNetwork/demo-pr-readiness">HBNetwork / demo-pr-readiness</a></header>
  <main>
    <div style="height: 900px; background: #123456"></div>
    <span data-component="StateLabel" data-status="${stateStatus}">state</span>
    <a href="/HBNetwork/demo-pr-readiness/pull/61/commits/e3d11a8171dbbb4af910b7c199a5f240dfb2441e">e3d11a8</a>
    <div class="timeline-comment-group" id="issuecomment-5312507139" ${hidden ? "hidden" : ""}>
      <a href="/apps/hamster-dan">hamster-dan bot</a>
      <h2>Hamsterdan review findings</h2>
      <p>${
        dashboard
          ? "checks:{'status': 'success'}<br>review:{'status': 'clear'}<br>announced:{'head': 'e3d11a8'}"
          : "Calculate lease duration in seconds"
      }</p>
    </div>
    ${
      duplicate
        ? `<div class="timeline-comment-group" id="issuecomment-5312507139">
             <a href="/apps/hamster-dan">hamster-dan bot</a>
             <p>Hamsterdan review findings — Calculate lease duration in seconds</p>
           </div>`
        : ""
    }
    ${script}
  </main>
</body></html>`;

const source = {
  gitCommit: "6763d5d9fd6850aee9aeac2deed9f4a5d9554be1",
  clean: true as const,
};

const manifestBytes = (): Uint8Array => Buffer.from(JSON.stringify(manifest()));

const capture = async (fixture: (url: URL, method: string) => FixtureResponse | undefined) => {
  const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-"));
  const result = await captureFixtureEvidence(manifestBytes(), {
    browser,
    outputRoot,
    source,
    now: new Date("2026-08-17T08:00:00Z"),
    fixture,
  });
  return {outputRoot, ...result};
};

describe("public GitHub checkpoint capture", () => {
  test("validates scoped evidence before publishing a bounded report and screenshot", async () => {
    process.env.CAPTURE_CREDENTIAL_CANARY = "never-copy-this-secret";
    const result = await capture(() => ({status: 200, body: pageHtml()}));
    const names = await readdir(result.directory);
    expect(names.sort()).toEqual(["checkpoints", "dom", "report.json"]);

    const screenshotNames = await readdir(join(result.directory, "checkpoints"));
    expect(screenshotNames).toEqual(["findings.png"]);
    const reportText = await readFile(join(result.directory, "report.json"), "utf8");
    expect(reportText).not.toContain("never-copy-this-secret");
    expect(reportText).not.toContain("Hamsterdan review findings");
    expect(reportText).not.toContain("cookie");
    expect(reportText).not.toContain("<html");

    const report = JSON.parse(reportText);
    expect(report.kind).toBe("github-fixture-checkpoint-capture");
    expect(report.source.gitCommit).toBe(source.gitCommit);
    expect(report.source.clean).toBeTrue();
    expect(report.source.manifestSha256).toBe(createHash("sha256").update(manifestBytes()).digest("hex"));
    expect(report.checkpoints[0].dimensions.width).toBe(1280);
    expect(report.checkpoints[0].assertions.map((item: {matched: boolean}) => item.matched).every(Boolean)).toBeTrue();
    expect(report.checkpoints[0].assertions.map((item: {id: string}) => item.id)).toEqual([
      "repository",
      "pull-request-state",
      "head",
      "target",
      "actor",
      "text-1",
      "text-2",
    ]);
    expect(report.video).toBeNull();
  });

  test("focuses an asserted dashboard line rendered inside one multiline element", async () => {
    const rawManifest = JSON.parse(JSON.stringify(manifest()));
    rawManifest.checkpoints[0].expectedText = ["review:{'status': 'clear'}"];
    rawManifest.checkpoints[0].focusText = "review:{'status': 'clear'}";
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-dashboard-"));
    const result = await captureFixtureEvidence(Buffer.from(JSON.stringify(rawManifest)), {
      browser,
      outputRoot,
      source,
      now: new Date("2026-08-17T08:00:00Z"),
      fixture: () => ({status: 200, body: pageHtml({dashboard: true})}),
    });
    expect(await readdir(result.directory)).toContain("report.json");
  });

  test("asserts the exact pull-request state the manifest declares", async () => {
    const closedManifest = JSON.parse(JSON.stringify(manifest()));
    closedManifest.expectedState = "closed";
    const captureClosed = (stateStatus: string) =>
      mkdtemp(join(tmpdir(), "hamsterdan-live-capture-state-")).then((outputRoot) =>
        captureFixtureEvidence(Buffer.from(JSON.stringify(closedManifest)), {
          browser,
          outputRoot,
          source,
          now: new Date("2026-08-17T08:00:00Z"),
          fixture: () => ({status: 200, body: pageHtml({stateStatus})}),
        }),
      );

    expect((await captureClosed("pullClosed")).report.checkpoints[0].id).toBe("findings");
    expect((await rejection(captureClosed("pullOpened"))).message).toMatch(/closed pull request/);
  });

  test("validates one explicit GitHub Actions run attempt", async () => {
    const rawManifest = JSON.parse(JSON.stringify(manifest()));
    rawManifest.actors.push({login: "github-actions", href: "/apps/github-actions"});
    rawManifest.checkpoints[0] = {
      id: "failed-attempt",
      kind: "actions-attempt",
      target: "31990573431/attempts/1",
      url: "https://github.com/HBNetwork/demo-pr-readiness/actions/runs/31990573431/attempts/1",
      actor: "github-actions",
      expectedText: ["You are viewing an older attempt", "Status", "Failure", "scenario-control"],
      focusText: "Failure",
      holdSeconds: 2,
    };
    const html = `<!doctype html><html><head><title>Demo · HBNetwork/demo-pr-readiness@e3d11a8 · GitHub</title></head>
      <body><main>
        <a href="/HBNetwork/demo-pr-readiness">HBNetwork / demo-pr-readiness</a>
        <a href="/apps/github-actions">github-actions[bot]</a>
        <p>#61</p><p>You are viewing an older attempt</p><p>Status</p><p>Failure</p><p>scenario-control</p>
      </main></body></html>`;
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-attempt-"));
    const result = await captureFixtureEvidence(Buffer.from(JSON.stringify(rawManifest)), {
      browser,
      outputRoot,
      source,
      now: new Date("2026-08-17T08:00:00Z"),
      fixture: () => ({status: 200, body: html}),
    });
    expect(result.report.checkpoints[0].target).toBe("31990573431/attempts/1");
  });

  test.each([
    ["missing text", pageHtml().replace("Calculate lease duration in seconds", "Different finding")],
    ["hidden target", pageHtml({hidden: true})],
    ["duplicate target", pageHtml({duplicate: true})],
    ["challenge page", "<html><body><main>Verify your identity</main></body></html>"],
  ])("fails closed without publishing media for a %s page", async (_name, html) => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-failed-"));
    await rejection(
      captureFixtureEvidence(manifestBytes(), {
        browser,
        outputRoot,
        source,
        now: new Date("2026-08-17T08:00:00Z"),
        fixture: () => ({status: 200, body: html}),
      }),
    );
    expect(await readdir(outputRoot)).toEqual([]);
  });

  test("rejects a redirect to login", async () => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-login-"));
    await rejection(
      captureFixtureEvidence(manifestBytes(), {
        browser,
        outputRoot,
        source,
        now: new Date("2026-08-17T08:00:00Z"),
        fixture: (url) =>
          url.pathname === "/login"
            ? {status: 200, body: "<html><body><main>Sign in to GitHub</main></body></html>"}
            : {status: 302, headers: {location: "https://github.com/login"}, body: ""},
      }),
    );
    expect(await readdir(outputRoot)).toEqual([]);
  });

  test("rejects a mutation-capable request made by the page", async () => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-post-"));
    const error = await rejection(
      captureFixtureEvidence(manifestBytes(), {
        browser,
        outputRoot,
        source,
        now: new Date("2026-08-17T08:00:00Z"),
        fixture: () => ({
          status: 200,
          body: pageHtml({script: `<script>fetch('/mutation', {method: 'POST', body: 'x'})</script>`}),
        }),
      }),
    );
    expect(error.message).toMatch(/read-only/);
    expect(await readdir(outputRoot)).toEqual([]);
  });

  test("blocks GitHub's known passive POST projections without misclassifying them as mutations", async () => {
    const result = await capture(() => ({
      status: 200,
      body: pageHtml({script: `<script>fetch('/commits/badges', {method: 'POST', body: 'projection'})</script>`}),
    }));
    expect(await readdir(result.directory)).toContain("report.json");
  });

  test("rejects a mutation attempted by the focus scroll after the early request check", async () => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-late-post-"));
    const script = `<script>
      const original = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function (...args) {
        fetch('/late-mutation', {method: 'POST', body: 'x'});
        return original.apply(this, args);
      };
    </script>`;
    const error = await rejection(
      captureFixtureEvidence(manifestBytes(), {
        browser,
        outputRoot,
        source,
        now: new Date("2026-08-17T08:00:00Z"),
        fixture: () => ({status: 200, body: pageHtml({script})}),
      }),
    );
    expect(error.message).toMatch(/read-only/);
    expect(await readdir(outputRoot)).toEqual([]);
  });
});

describe("full-page and full-state checkpoint evidence", () => {
  test("keeps the rendered DOM from both sides of the checkpoint action", async () => {
    const result = await capture(() => ({status: 200, body: pageHtml()}));
    expect((await readdir(join(result.directory, "dom"))).sort()).toEqual([
      "findings.after.html",
      "findings.before.html",
    ]);

    const checkpoint = result.report.checkpoints[0];
    expect(checkpoint.dom.before.file).toBe("dom/findings.before.html");
    expect(checkpoint.dom.after.file).toBe("dom/findings.after.html");
    for (const phase of ["before", "after"] as const) {
      const recorded = checkpoint.dom[phase];
      const bytes = await readFile(join(result.directory, recorded.file));
      expect(bytes.byteLength).toBe(recorded.byteLength);
      expect(createHash("sha256").update(bytes).digest("hex")).toBe(recorded.sha256);
      expect(bytes.toString("utf8")).toContain("Hamsterdan review findings");
    }
  });

  test("publishes a full-page still whose pixel height is the page's own scrollHeight", async () => {
    const result = await capture(() => ({status: 200, body: pageHtml()}));
    const checkpoint = result.report.checkpoints[0];
    const bytes = await readFile(join(result.directory, checkpoint.file));
    const observed = pngDimensions(bytes);

    expect(checkpoint.capture.fullPage).toBeTrue();
    expect(observed.width).toBe(1280);
    expect(observed.height).toBe(checkpoint.capture.scrollHeight);
    expect(observed).toEqual(checkpoint.dimensions);
    // The fixture page is deliberately longer than the 720px viewport, so a
    // viewport-only screenshot could never satisfy this.
    expect(observed.height).toBeGreaterThan(720);
  });

  test("verifies the still against max(body, documentElement) scrollHeight", async () => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-doc-height-"));
    // A trailing body margin escapes the body box, so document.body.scrollHeight
    // runs short of the page the browser actually paints. The ruling amendment
    // makes documentElement.scrollHeight the height the still must match.
    const result = await captureFixtureEvidence(manifestBytes(), {
      browser,
      outputRoot,
      source,
      now: new Date("2026-08-17T08:00:00Z"),
      fixture: () => ({status: 200, body: pageHtml({style: "body{margin:40px;display:flow-root}"})}),
    });
    const checkpoint = result.report.checkpoints[0];
    const observed = pngDimensions(await readFile(join(result.directory, checkpoint.file)));
    expect(observed.height).toBe(checkpoint.capture.scrollHeight);

    // The same page without the margin is exactly 80px shorter, which is the
    // height document.body.scrollHeight would still have reported here — the
    // amount the body-only check used to lose.
    const plain = await capture(() => ({status: 200, body: pageHtml()}));
    expect(checkpoint.capture.scrollHeight).toBe(plain.report.checkpoints[0].capture.scrollHeight + 80);
  });

  test("fails closed when the still can never match the page's real height", async () => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-cropped-"));
    // Both scrollHeight readings are forced below the painted page, so every
    // attempt produces a still the ruling calls cropped.
    const script = `<script>
      Object.defineProperty(Element.prototype, "scrollHeight", {configurable: true, get: () => 1});
    </script>`;
    const error = await rejection(
      captureFixtureEvidence(manifestBytes(), {
        browser,
        outputRoot,
        source,
        now: new Date("2026-08-17T08:00:00Z"),
        fixture: () => ({status: 200, body: pageHtml({script})}),
      }),
    );
    expect(error.message).toMatch(/cropped after 3 attempts/);
    expect(await readdir(outputRoot)).toEqual([]);
  });

  test("records the checkpoint target's document-coordinate anchor box", async () => {
    const result = await capture(() => ({status: 200, body: pageHtml()}));
    const checkpoint = result.report.checkpoints[0];
    // The fixture puts a 900px spacer above the comment, so the anchor cannot
    // be a viewport-relative box: it has to be the position on the whole page.
    expect(checkpoint.anchor.y).toBeGreaterThan(720);
    expect(checkpoint.anchor.y).toBeLessThan(checkpoint.dimensions.height);
    expect(checkpoint.anchor.height).toBeGreaterThan(0);
    expect(checkpoint.anchor.x + checkpoint.anchor.width).toBeLessThanOrEqual(checkpoint.dimensions.width);
  });

  test("writes no PDF anywhere in the published capture", async () => {
    const result = await capture(() => ({status: 200, body: pageHtml()}));
    const entries = await readdir(result.directory, {recursive: true});
    expect(entries.filter((name) => name.endsWith(".pdf"))).toEqual([]);
    expect(entries.length).toBeGreaterThan(0);
  });
});
