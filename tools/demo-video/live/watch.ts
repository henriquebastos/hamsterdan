import {mkdir, rename, rm, writeFile} from "node:fs/promises";
import {join} from "node:path";
import {createRequire} from "node:module";
import type {Page} from "playwright";
import {archivePage} from "./archive";
import {
  assertion,
  captureFullPage,
  normalizeText,
  openReadOnlyContext,
  sha256,
  STATE_LABEL_STATUS,
  timestampSlug,
  validateSource,
  visibleCount,
  type AssertionReport,
  type CaptureOptions,
  type DomReport,
  type Fixture,
} from "./capture";
import {parseManifest, watchedPageUrl, type CaptureManifest, type WatchPlan} from "./manifest";

export type StateReport = Readonly<{
  id: string;
  kind: "state";
  target: string;
  requestedUrl: string;
  finalUrl: string;
  capturedAt: string;
  file: string;
  sha256: string;
  dimensions: Readonly<{width: number; height: number}>;
  capture: Readonly<{fullPage: true; scrollHeight: number; attempts: number}>;
  dom: Readonly<{before: DomReport; after: DomReport}>;
  // A watched page state has no single target element to frame, so the
  // transition renderer falls back to the pixels that changed.
  anchor: null;
  scope: Readonly<{normalizedTextLength: number; normalizedTextSha256: string}>;
  assertions: readonly AssertionReport[];
}>;

export type StateSequenceKind = "github-live-state-sequence-capture" | "github-fixture-state-sequence-capture";

export type StateSequenceReport = Readonly<{
  schema: 1;
  kind: StateSequenceKind;
  slug: string;
  capturedAt: string;
  source: Readonly<{gitCommit: string; clean: true; manifestSha256: string}>;
  runtime: Readonly<Record<string, unknown>>;
  checkpoints: readonly StateReport[];
  video: null;
}>;

export type WatchOverrides = Readonly<{pollSeconds?: number; durationSeconds?: number}>;

export type WatchOptions = CaptureOptions & WatchOverrides;

export type FixtureWatchOptions = WatchOptions & Readonly<{fixture: Fixture}>;

export const resolveWatchPlan = (manifest: CaptureManifest, overrides: WatchOverrides): WatchPlan => {
  if (!manifest.watch) {
    throw new Error(`manifest ${manifest.slug} declares no watch plan`);
  }
  const plan = {
    ...manifest.watch,
    ...(overrides.pollSeconds === undefined ? {} : {pollSeconds: overrides.pollSeconds}),
    ...(overrides.durationSeconds === undefined ? {} : {durationSeconds: overrides.durationSeconds}),
  };
  if (!Number.isInteger(plan.pollSeconds) || plan.pollSeconds < 1 || plan.pollSeconds > 60) {
    throw new Error("watch poll cadence must be between 1 and 60 seconds");
  }
  if (!Number.isInteger(plan.durationSeconds) || plan.durationSeconds < 2 || plan.durationSeconds > 900) {
    throw new Error("watch duration must be between 2 and 900 seconds");
  }
  if (plan.pollSeconds > plan.durationSeconds) {
    throw new Error("watch poll cadence must fit inside the watch duration");
  }
  return plan;
};

export const stateId = (ordinal: number): string => `state-${String(ordinal).padStart(3, "0")}`;

// The watched page is validated on every poll, not only when it changed, so a
// journey that drifts to another repository, pull-request state, or a
// challenge page fails the whole run instead of silently recording it.
const validateWatchedPage = async (
  page: Page,
  manifest: CaptureManifest,
  url: string,
  label: string,
): Promise<{assertions: AssertionReport[]; text: string}> => {
  if (page.url() !== url) {
    throw new Error(`${label} redirected to an unexpected identity`);
  }
  const title = await page.title();
  const text = normalizeText(await page.locator("body").innerText());
  if (
    title.length === 0 ||
    /Sign in to GitHub|Verify your identity|rate limit|Whoa there|Page not found/i.test(`${title} ${text}`)
  ) {
    throw new Error(`${label} is unavailable without authentication`);
  }

  const assertions: AssertionReport[] = [];
  if ((await visibleCount(page.locator(`a[href="/${manifest.repository}"]`))) < 1) {
    throw new Error(`${label} does not show the expected repository`);
  }
  assertions.push(assertion("repository", manifest.repository));

  const status = STATE_LABEL_STATUS[manifest.expectedState];
  if ((await visibleCount(page.locator(`[data-component="StateLabel"][data-status="${status}"]`))) < 1) {
    throw new Error(`${label} does not show a ${manifest.expectedState} pull request`);
  }
  assertions.push(assertion("pull-request-state", manifest.expectedState));

  const present: string[] = [];
  for (const actor of manifest.actors) {
    if ((await visibleCount(page.locator(`a[href="${actor.href}"]`))) >= 1) present.push(actor.login);
  }
  if (present.length === 0) {
    throw new Error(`${label} shows none of the declared actors`);
  }
  assertions.push(assertion("actor", present.join(",")));
  return {assertions, text};
};

const sleep = (milliseconds: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });

const watchEvidence = async (
  manifestBytes: Uint8Array,
  options: WatchOptions,
  kind: StateSequenceKind,
  fixture?: Fixture,
): Promise<{directory: string; report: StateSequenceReport}> => {
  validateSource(options.source);
  const manifestSha256 = sha256(manifestBytes);
  const manifest = parseManifest(JSON.parse(Buffer.from(manifestBytes).toString("utf8")));
  const plan = resolveWatchPlan(manifest, options);
  const url = watchedPageUrl(manifest);
  const capturedAt = options.now.toISOString();
  const name = `${timestampSlug(options.now)}-${manifestSha256.slice(0, 12)}`;
  const finalDirectory = join(options.outputRoot, name);
  const temporaryDirectory = join(options.outputRoot, `.tmp-${name}-${crypto.randomUUID()}`);
  await mkdir(join(temporaryDirectory, "checkpoints"), {recursive: true});
  await mkdir(join(temporaryDirectory, "dom"), {recursive: true});

  const writeDom = async (id: string, phase: "before" | "after", html: string): Promise<DomReport> => {
    const relativeFile = `dom/${id}.${phase}.html`;
    const bytes = Buffer.from(html, "utf8");
    await writeFile(join(temporaryDirectory, relativeFile), bytes, {flag: "wx"});
    return {file: relativeFile, sha256: sha256(bytes), byteLength: bytes.byteLength};
  };

  let opened;
  try {
    opened = await openReadOnlyContext(options.browser, manifest.viewport, fixture);
  } catch (error) {
    await rm(temporaryDirectory, {recursive: true, force: true});
    throw error;
  }
  const {context, unsafeRequests} = opened;

  const page = await context.newPage();
  const states: StateReport[] = [];
  let contextClosed = false;
  try {
    const startedAt = Date.now();
    const deadline = startedAt + plan.durationSeconds * 1000;
    let previousTextSha256 = "";
    let ordinal = 0;
    let polls = 0;

    while (states.length < plan.maxStates) {
      polls += 1;
      const label = `watch poll ${polls}`;
      if (polls === 1) {
        const response = await page.goto(url, {waitUntil: "domcontentloaded", timeout: 30_000});
        if (!response || response.status() < 200 || response.status() >= 300) {
          throw new Error(`${label} did not return a successful document`);
        }
      } else {
        const response = await page.reload({waitUntil: "domcontentloaded", timeout: 30_000});
        if (!response || response.status() < 200 || response.status() >= 300) {
          throw new Error(`${label} did not return a successful document`);
        }
      }
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(150);
      if (unsafeRequests.length > 0) {
        throw new Error(`${label} violated the read-only boundary`);
      }
      const beforeHtml = await archivePage(page);
      const validated = await validateWatchedPage(page, manifest, url, label);
      const textSha256 = sha256(validated.text);

      if (textSha256 !== previousTextSha256) {
        ordinal += 1;
        const id = stateId(ordinal);
        const before = await writeDom(id, "before", beforeHtml);
        const after = await writeDom(id, "after", await archivePage(page));
        const full = await captureFullPage(page, `state ${id}`, manifest.viewport);
        const relativeFile = `checkpoints/${id}.png`;
        await writeFile(join(temporaryDirectory, relativeFile), full.png, {flag: "wx"});
        states.push({
          id,
          kind: "state",
          target: String(ordinal),
          requestedUrl: url,
          finalUrl: page.url(),
          capturedAt: new Date(options.now.getTime() + (Date.now() - startedAt)).toISOString(),
          file: relativeFile,
          sha256: sha256(full.png),
          dimensions: full.dimensions,
          capture: {fullPage: true, scrollHeight: full.scrollHeight, attempts: full.attempts},
          dom: {before, after},
          anchor: null,
          scope: {normalizedTextLength: validated.text.length, normalizedTextSha256: textSha256},
          assertions: [...validated.assertions, assertion("state-ordinal", String(ordinal))],
        });
        previousTextSha256 = textSha256;
      }

      if (Date.now() + plan.pollSeconds * 1000 > deadline) break;
      await sleep(plan.pollSeconds * 1000);
    }

    await page.close();
    await context.close();
    contextClosed = true;
    if (unsafeRequests.length > 0) {
      throw new Error("watch violated the read-only boundary after state validation");
    }
    if (states.length < 2) {
      throw new Error(`watched journey observed ${states.length} state(s); a transition render needs at least two`);
    }

    const require = createRequire(import.meta.url);
    const report: StateSequenceReport = {
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
      checkpoints: states,
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

export const watchPublicStates = (
  manifestBytes: Uint8Array,
  options: WatchOptions,
): Promise<{directory: string; report: StateSequenceReport}> =>
  watchEvidence(manifestBytes, options, "github-live-state-sequence-capture");

export const watchFixtureStates = (
  manifestBytes: Uint8Array,
  options: FixtureWatchOptions,
): Promise<{directory: string; report: StateSequenceReport}> => {
  const {fixture, ...watchOptions} = options;
  return watchEvidence(manifestBytes, watchOptions, "github-fixture-state-sequence-capture", fixture);
};
