import {createHash} from "node:crypto";
import {mkdir, rename, rm, writeFile} from "node:fs/promises";
import {join} from "node:path";
import {createRequire} from "node:module";
import type {Browser, BrowserContext, Locator, Page} from "playwright";
import {archivePage} from "./archive";
import {parseManifest, type CaptureManifest, type Checkpoint, type PullRequestState} from "./manifest";
import {pngDimensions} from "./png";
import type {Region} from "./region";

export type FixtureResponse = Readonly<{
  status: number;
  headers?: Readonly<Record<string, string>>;
  body: string;
}>;

export type CaptureSource = Readonly<{
  gitCommit: string;
  clean: true;
}>;

export type CaptureOptions = Readonly<{
  browser: Browser;
  outputRoot: string;
  source: CaptureSource;
  now: Date;
}>;

export type Fixture = (url: URL, method: string) => FixtureResponse | undefined | Promise<FixtureResponse | undefined>;

export type FixtureCaptureOptions = CaptureOptions &
  Readonly<{
    fixture: Fixture;
  }>;

export type AssertionReport = Readonly<{
  id: string;
  matched: true;
  expectedSha256: string;
}>;

export type DomReport = Readonly<{
  file: string;
  sha256: string;
  byteLength: number;
}>;

export type CheckpointReport = Readonly<{
  id: string;
  kind: Checkpoint["kind"];
  target: string;
  requestedUrl: string;
  finalUrl: string;
  capturedAt: string;
  file: string;
  sha256: string;
  dimensions: Readonly<{width: number; height: number}>;
  capture: Readonly<{fullPage: true; scrollHeight: number; attempts: number}>;
  dom: Readonly<{before: DomReport; after: DomReport}>;
  // Document-coordinate bounding box of the checkpoint's target element, so a
  // static journey can still be framed readably when consecutive stills carry
  // no meaningful pixel difference.
  anchor: Region;
  scope: Readonly<{normalizedTextLength: number; normalizedTextSha256: string}>;
  assertions: readonly AssertionReport[];
}>;

export type CaptureReport = Readonly<{
  schema: 1;
  kind: "github-live-checkpoint-capture" | "github-fixture-checkpoint-capture";
  slug: string;
  capturedAt: string;
  source: CaptureSource & Readonly<{manifestSha256: string}>;
  runtime: Readonly<{
    bunVersion: string;
    playwrightVersion: string;
    browserVersion: string;
    viewport: Readonly<{width: number; height: number}>;
    deviceScaleFactor: 1;
    locale: "en-US";
    timezoneId: "UTC";
    colorScheme: "dark";
    reducedMotion: "reduce";
  }>;
  checkpoints: readonly CheckpointReport[];
  video: null;
}>;

const ALLOWED_HOSTS = new Set([
  "github.com",
  "github.githubassets.com",
  "avatars.githubusercontent.com",
  "camo.githubusercontent.com",
  "user-images.githubusercontent.com",
  "private-user-images.githubusercontent.com",
]);

const isPassiveGitHubPost = (url: URL): boolean =>
  (url.hostname === "collector.github.com" && url.pathname === "/github/collect") ||
  (url.hostname === "api.github.com" && url.pathname === "/_private/browser/stats") ||
  (url.hostname === "github.com" && url.pathname === "/commits/badges") ||
  (url.hostname === "github.com" && /^\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/commits\/checks-statuses-rollups$/.test(url.pathname));

export const sha256 = (value: string | Uint8Array): string => createHash("sha256").update(value).digest("hex");
export const normalizeText = (value: string): string => value.replace(/\s+/g, " ").trim();

export const visibleCount = (locator: Locator): Promise<number> =>
  locator.evaluateAll((elements) =>
    elements.filter((element) => (element as HTMLElement).checkVisibility({checkOpacity: true, checkVisibilityCSS: true}))
      .length,
  );

const requireVisible = async (locator: Locator, label: string, expected = 1): Promise<void> => {
  const count = await visibleCount(locator);
  if (count !== expected) {
    throw new Error(`${label} expected ${expected} visible match, found ${count}`);
  }
};

export const assertion = (id: string, expected: string): AssertionReport => ({
  id,
  matched: true,
  expectedSha256: sha256(normalizeText(expected)),
});

export const STATE_LABEL_STATUS: Readonly<Record<PullRequestState, string>> = {
  open: "pullOpened",
  closed: "pullClosed",
  merged: "pullMerged",
};

// The 2026-09-02 evidence ruling: a still is only evidence when it shows the
// whole page, so a full-page PNG must be exactly as tall as the page's own real
// height. That height is max(document.body.scrollHeight,
// document.documentElement.scrollHeight) — the body number alone runs short
// whenever a trailing margin escapes the body box. A browser never renders
// below the viewport, so a page shorter than the viewport is exactly one
// viewport tall.
export const expectedStillHeight = (scrollHeight: number, viewportHeight: number): number =>
  Math.max(scrollHeight, viewportHeight);

export const pageScrollHeight = (page: Page): Promise<number> =>
  page.evaluate(() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight));

// Document-coordinate box, so it stays valid against a full-page still no
// matter where the page happens to be scrolled when it is measured.
export const documentBox = (locator: Locator): Promise<Region> =>
  locator.first().evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      x: Math.max(0, Math.round(rect.left + window.scrollX)),
      y: Math.max(0, Math.round(rect.top + window.scrollY)),
      width: Math.max(1, Math.round(rect.width)),
      height: Math.max(1, Math.round(rect.height)),
    };
  });

const FULL_PAGE_ATTEMPTS = 3;

export const captureFullPage = async (
  page: Page,
  label: string,
  viewport: Readonly<{width: number; height: number}>,
): Promise<{png: Uint8Array; dimensions: {width: number; height: number}; scrollHeight: number; attempts: number}> => {
  let observed = "";
  for (let attempt = 1; attempt <= FULL_PAGE_ATTEMPTS; attempt += 1) {
    const scrollHeight = await pageScrollHeight(page);
    const png = await page.screenshot({type: "png", fullPage: true, animations: "disabled", caret: "hide"});
    const dimensions = pngDimensions(png, `${label} screenshot`);
    if (dimensions.width === viewport.width && dimensions.height === expectedStillHeight(scrollHeight, viewport.height)) {
      return {png, dimensions, scrollHeight, attempts: attempt};
    }
    observed = `${dimensions.width}x${dimensions.height} against viewport ${viewport.width}x${viewport.height} and page height ${scrollHeight}`;
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(250);
  }
  throw new Error(`${label} full-page screenshot stayed cropped after ${FULL_PAGE_ATTEMPTS} attempts: ${observed}`);
};

const checkpointScope = (page: Page, checkpoint: Checkpoint): Locator => {
  switch (checkpoint.kind) {
    case "issue-comment":
      return page.locator(`div.timeline-comment-group#issuecomment-${checkpoint.target}`);
    case "review":
      return page.locator(`div.timeline-comment-group#pullrequestreview-${checkpoint.target}`);
    case "commit":
    case "pr-checks":
    case "actions-run":
    case "actions-attempt":
      return page.locator("main");
  }
};

const validatePage = async (
  page: Page,
  manifest: CaptureManifest,
  checkpoint: Checkpoint,
): Promise<{scope: Locator; scopeText: string; anchor: Region; assertions: AssertionReport[]}> => {
  if (page.url() !== checkpoint.url) {
    throw new Error(`checkpoint ${checkpoint.id} redirected to an unexpected identity`);
  }
  const title = await page.title();
  const bodyText = normalizeText(await page.locator("body").innerText());
  if (
    title.length === 0 ||
    /Sign in to GitHub|Verify your identity|rate limit|Whoa there|Page not found/i.test(`${title} ${bodyText}`)
  ) {
    throw new Error(`checkpoint ${checkpoint.id} is unavailable without authentication`);
  }

  const assertions: AssertionReport[] = [];
  const repository = page.locator(`a[href="/${manifest.repository}"]`);
  if ((await visibleCount(repository)) < 1) {
    throw new Error(`checkpoint ${checkpoint.id} does not show the expected repository`);
  }
  assertions.push(assertion("repository", manifest.repository));

  if (checkpoint.kind === "issue-comment" || checkpoint.kind === "review" || checkpoint.kind === "pr-checks") {
    const status = STATE_LABEL_STATUS[manifest.expectedState];
    const stateLabel = page.locator(`[data-component="StateLabel"][data-status="${status}"]`);
    if ((await visibleCount(stateLabel)) < 1) {
      throw new Error(`checkpoint ${checkpoint.id} does not show a ${manifest.expectedState} pull request`);
    }
    assertions.push(assertion("pull-request-state", manifest.expectedState));
  }

  if (checkpoint.kind === "commit") {
    if (!bodyText.includes(manifest.expectedHead.slice(0, 7))) {
      throw new Error(`checkpoint ${checkpoint.id} does not show the expected commit`);
    }
    assertions.push(assertion("head", manifest.expectedHead));
  } else if (checkpoint.kind === "pr-checks") {
    const embeddedHead = await page.locator("script").evaluateAll(
      (elements, expectedHead) => elements.some((element) => element.textContent?.includes(expectedHead)),
      manifest.expectedHead,
    );
    const run = page.locator(`a[href="/${manifest.repository}/actions/runs/${checkpoint.target}"]`);
    if (!embeddedHead || !bodyText.includes(manifest.expectedHead.slice(0, 7)) || (await visibleCount(run)) < 1) {
      throw new Error(`checkpoint ${checkpoint.id} does not identify the expected head and Actions run`);
    }
    assertions.push(assertion("head", manifest.expectedHead));
    assertions.push(assertion("run", checkpoint.target));
  } else if (checkpoint.kind === "actions-run" || checkpoint.kind === "actions-attempt") {
    if (!bodyText.includes(`#${manifest.pullRequest}`) || !title.includes(manifest.expectedHead.slice(0, 7))) {
      throw new Error(`checkpoint ${checkpoint.id} does not identify the expected pull request and head`);
    }
    assertions.push(assertion("head", manifest.expectedHead));
    assertions.push(assertion("run", checkpoint.target));
  } else {
    const head = page.locator(
      `a[href="/${manifest.repository}/pull/${manifest.pullRequest}/commits/${manifest.expectedHead}"]`,
    );
    if ((await visibleCount(head)) < 1) {
      throw new Error(`checkpoint ${checkpoint.id} does not show the expected head`);
    }
    assertions.push(assertion("head", manifest.expectedHead));
  }

  const scope = checkpointScope(page, checkpoint);
  await requireVisible(scope, `checkpoint ${checkpoint.id} target`);
  assertions.push(assertion("target", `${checkpoint.kind}:${checkpoint.target}`));

  const actor = manifest.actors.find(({login}) => login === checkpoint.actor);
  if (!actor) {
    throw new Error(`checkpoint ${checkpoint.id} has an undeclared actor`);
  }
  if ((await visibleCount(scope.locator(`a[href="${actor.href}"]`))) < 1) {
    throw new Error(`checkpoint ${checkpoint.id} does not show the expected actor`);
  }
  assertions.push(assertion("actor", `${actor.login}:${actor.href}`));

  const scopeText = normalizeText(await scope.innerText());
  for (const [index, expected] of checkpoint.expectedText.entries()) {
    if (!scopeText.includes(normalizeText(expected))) {
      throw new Error(`checkpoint ${checkpoint.id} is missing expected text ${index + 1}`);
    }
    assertions.push(assertion(`text-${index + 1}`, expected));
  }

  const focus = scope.getByText(checkpoint.focusText, {exact: false});
  if ((await visibleCount(focus)) < 1) {
    throw new Error(`checkpoint ${checkpoint.id} focus is not visibly scoped to its target`);
  }
  await focus.first().evaluate((element) => element.scrollIntoView({block: "center", inline: "nearest"}));
  await page.waitForTimeout(50);
  return {scope, scopeText, anchor: await documentBox(scope), assertions};
};

// One definition of the anonymous, nonpersistent, strictly read-only browsing
// surface, shared by the manifest-checkpoint lane and the watched state lane so
// neither can drift away from the other's security properties.
export const openReadOnlyContext = async (
  browser: Browser,
  viewport: Readonly<{width: number; height: number}>,
  fixture?: Fixture,
): Promise<{context: BrowserContext; unsafeRequests: string[]}> => {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    locale: "en-US",
    timezoneId: "UTC",
    colorScheme: "dark",
    reducedMotion: "reduce",
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  const initialStorage = await context.storageState();
  if (initialStorage.cookies.length !== 0 || initialStorage.origins.length !== 0) {
    await context.close();
    throw new Error("live capture browser context did not start empty");
  }

  const unsafeRequests: string[] = [];
  await context.route("**/*", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    if (method !== "GET" && method !== "HEAD") {
      if (method !== "POST" || !isPassiveGitHubPost(url)) {
        unsafeRequests.push(`${method} ${url.origin}${url.pathname}`);
      }
      await route.abort("blockedbyclient");
      return;
    }
    if (url.protocol !== "https:" || !ALLOWED_HOSTS.has(url.hostname) || url.username !== "" || url.password !== "") {
      await route.abort("blockedbyclient");
      return;
    }
    const response = await fixture?.(url, method);
    if (response) {
      await route.fulfill({status: response.status, headers: response.headers, body: response.body, contentType: "text/html"});
      return;
    }
    await route.continue();
  });
  return {context, unsafeRequests};
};

export const timestampSlug = (instant: Date): string => instant.toISOString().replace(/[-:]/g, "").replace(".000", "");

export const validateSource = (source: CaptureSource): void => {
  if (!/^[0-9a-f]{40}$/.test(source.gitCommit) || source.clean !== true) {
    throw new Error("capture source must identify a clean committed revision");
  }
};

const captureEvidence = async (
  manifestBytes: Uint8Array,
  options: CaptureOptions,
  kind: CaptureReport["kind"],
  fixture?: FixtureCaptureOptions["fixture"],
): Promise<{directory: string; report: CaptureReport}> => {
  validateSource(options.source);
  const manifestSha256 = sha256(manifestBytes);
  const manifest = parseManifest(JSON.parse(Buffer.from(manifestBytes).toString("utf8")));
  const capturedAt = options.now.toISOString();
  const name = `${timestampSlug(options.now)}-${manifestSha256.slice(0, 12)}`;
  const finalDirectory = join(options.outputRoot, name);
  const temporaryDirectory = join(options.outputRoot, `.tmp-${name}-${crypto.randomUUID()}`);
  const checkpointDirectory = join(temporaryDirectory, "checkpoints");
  await mkdir(checkpointDirectory, {recursive: true});
  await mkdir(join(temporaryDirectory, "dom"), {recursive: true});

  const writeDom = async (checkpointId: string, phase: "before" | "after", html: string): Promise<DomReport> => {
    const relativeFile = `dom/${checkpointId}.${phase}.html`;
    const bytes = Buffer.from(html, "utf8");
    await writeFile(join(temporaryDirectory, relativeFile), bytes, {flag: "wx"});
    return {file: relativeFile, sha256: sha256(bytes), byteLength: bytes.byteLength};
  };

  let opened: {context: BrowserContext; unsafeRequests: string[]};
  try {
    opened = await openReadOnlyContext(options.browser, manifest.viewport, fixture);
  } catch (error) {
    await rm(temporaryDirectory, {recursive: true, force: true});
    throw error;
  }
  const {context, unsafeRequests} = opened;

  const page = await context.newPage();
  const checkpoints: CheckpointReport[] = [];
  let contextClosed = false;
  try {
    for (const checkpoint of manifest.checkpoints) {
      if (page.url() !== checkpoint.url) {
        const previousDocument = page.url().split("#", 1)[0];
        const targetDocument = checkpoint.url.split("#", 1)[0];
        const response = await page.goto(checkpoint.url, {waitUntil: "domcontentloaded", timeout: 30_000});
        const sameDocument = response === null && previousDocument === targetDocument && page.url() === checkpoint.url;
        if (!sameDocument && (!response || response.status() < 200 || response.status() >= 300)) {
          throw new Error(`checkpoint ${checkpoint.id} did not return a successful document`);
        }
      }
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(150);
      if (unsafeRequests.length > 0) {
        throw new Error(`checkpoint ${checkpoint.id} violated the read-only boundary`);
      }
      // Layer 1 of the evidence ruling: the rendered DOM on both sides of the
      // action this checkpoint performs on the page (its focus scroll).
      const before = await writeDom(checkpoint.id, "before", await archivePage(page));
      const validated = await validatePage(page, manifest, checkpoint);
      const after = await writeDom(checkpoint.id, "after", await archivePage(page));
      const full = await captureFullPage(page, `checkpoint ${checkpoint.id}`, manifest.viewport);
      const relativeFile = `checkpoints/${checkpoint.id}.png`;
      await writeFile(join(temporaryDirectory, relativeFile), full.png, {flag: "wx"});
      checkpoints.push({
        id: checkpoint.id,
        kind: checkpoint.kind,
        target: checkpoint.target,
        requestedUrl: checkpoint.url,
        finalUrl: page.url(),
        capturedAt,
        file: relativeFile,
        sha256: sha256(full.png),
        dimensions: full.dimensions,
        capture: {fullPage: true, scrollHeight: full.scrollHeight, attempts: full.attempts},
        dom: {before, after},
        anchor: validated.anchor,
        scope: {
          normalizedTextLength: validated.scopeText.length,
          normalizedTextSha256: sha256(validated.scopeText),
        },
        assertions: validated.assertions,
      });
    }

    await page.close();
    await context.close();
    contextClosed = true;
    if (unsafeRequests.length > 0) {
      throw new Error("capture violated the read-only boundary after checkpoint validation");
    }

    const require = createRequire(import.meta.url);
    const report: CaptureReport = {
      schema: 1,
      kind,
      slug: manifest.slug,
      capturedAt,
      source: {...options.source, manifestSha256},
      runtime: {
        bunVersion: Bun.version,
        playwrightVersion: require("playwright/package.json").version as string,
        browserVersion: options.browser.version(),
        viewport: manifest.viewport,
        deviceScaleFactor: 1,
        locale: "en-US",
        timezoneId: "UTC",
        colorScheme: "dark",
        reducedMotion: "reduce",
      },
      checkpoints,
      video: null,
    };
    await writeFile(join(temporaryDirectory, "report.json"), `${JSON.stringify(report, null, 2)}\n`, {flag: "wx"});
    await rename(temporaryDirectory, finalDirectory);
    return {directory: finalDirectory, report};
  } catch (error) {
    await rm(temporaryDirectory, {recursive: true, force: true});
    throw error;
  } finally {
    if (!contextClosed) {
      await context.close();
    }
  }
};

export const capturePublicEvidence = (
  manifestBytes: Uint8Array,
  options: CaptureOptions,
): Promise<{directory: string; report: CaptureReport}> =>
  captureEvidence(manifestBytes, options, "github-live-checkpoint-capture");

export const captureFixtureEvidence = (
  manifestBytes: Uint8Array,
  options: FixtureCaptureOptions,
): Promise<{directory: string; report: CaptureReport}> => {
  const {fixture, ...captureOptions} = options;
  return captureEvidence(manifestBytes, captureOptions, "github-fixture-checkpoint-capture", fixture);
};
