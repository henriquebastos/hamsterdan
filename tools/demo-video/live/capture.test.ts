import {afterAll, beforeAll, describe, expect, test} from "bun:test";
import {createHash} from "node:crypto";
import {mkdtemp, readdir, readFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium, type Browser} from "playwright";
import {captureFixtureEvidence, type FixtureResponse} from "./capture";
import {parseManifest, type CaptureManifest} from "./manifest";

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

const pageHtml = ({hidden = false, duplicate = false, dashboard = false, script = ""} = {}) => `<!doctype html>
<html><head><title>Hamsterdan demo · Pull Request #61 · HBNetwork/demo-pr-readiness</title></head>
<body>
  <header><a href="/HBNetwork/demo-pr-readiness">HBNetwork / demo-pr-readiness</a></header>
  <main>
    <span data-component="StateLabel" data-status="pullOpened">Open</span>
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
    expect(names.sort()).toEqual(["checkpoints", "report.json"]);

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
    expect(report.checkpoints[0].dimensions).toEqual({width: 1280, height: 720});
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

  test.each([
    ["missing text", pageHtml().replace("Calculate lease duration in seconds", "Different finding")],
    ["hidden target", pageHtml({hidden: true})],
    ["duplicate target", pageHtml({duplicate: true})],
    ["challenge page", "<html><body><main>Verify your identity</main></body></html>"],
  ])("fails closed without publishing media for a %s page", async (_name, html) => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-failed-"));
    await expect(
      captureFixtureEvidence(manifestBytes(), {
        browser,
        outputRoot,
        source,
        now: new Date("2026-08-17T08:00:00Z"),
        fixture: () => ({status: 200, body: html}),
      }),
    ).rejects.toThrow();
    expect(await readdir(outputRoot)).toEqual([]);
  });

  test("rejects a redirect to login", async () => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-login-"));
    await expect(
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
    ).rejects.toThrow();
    expect(await readdir(outputRoot)).toEqual([]);
  });

  test("rejects a mutation-capable request made by the page", async () => {
    const outputRoot = await mkdtemp(join(tmpdir(), "hamsterdan-live-capture-post-"));
    await expect(
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
    ).rejects.toThrow(/read-only/);
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
    await expect(
      captureFixtureEvidence(manifestBytes(), {
        browser,
        outputRoot,
        source,
        now: new Date("2026-08-17T08:00:00Z"),
        fixture: () => ({status: 200, body: pageHtml({script})}),
      }),
    ).rejects.toThrow(/read-only/);
    expect(await readdir(outputRoot)).toEqual([]);
  });
});
