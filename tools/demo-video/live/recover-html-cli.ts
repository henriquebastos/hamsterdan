import {readFile, writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {chromium} from "playwright";
import {archivePage} from "./archive";
import {openReadOnlyContext, sha256} from "./capture";

const [input, output, theme, url] = process.argv.slice(2);
if (!input || !output || !["light", "dark"].includes(theme) || !/^https:\/\/github\.com\/HBNetwork\/demo-pr-readiness\/pull\/\d+$/.test(url)) {
  throw new Error("Usage: bun run live/recover-html-cli.ts INPUT.html OUTPUT.html light|dark https://github.com/HBNetwork/demo-pr-readiness/pull/NUMBER");
}
const original = await readFile(input, "utf8");
const browser = await chromium.launch();
try {
  const {context, unsafeRequests} = await openReadOnlyContext(browser, {width: 1280, height: 720});
  const page = await context.newPage();
  const restored = await page.evaluate(({original, theme, url}) => {
    const doc = new DOMParser().parseFromString(original, "text/html");
    doc.querySelectorAll("script, base, meta[http-equiv], link[rel=preload], link[rel=modulepreload], link[rel=prefetch]").forEach((node) => node.remove());
    doc.documentElement.lang = "en";
    doc.documentElement.setAttribute("data-color-mode", theme);
    doc.documentElement.setAttribute("data-light-theme", "light");
    doc.documentElement.setAttribute("data-dark-theme", "dark");
    doc.documentElement.className = "js-skip-scroll-target-into-view js-focus-visible";
    doc.documentElement.setAttribute("data-a11y-animated-images", "system");
    doc.documentElement.setAttribute("data-a11y-link-underlines", "true");
    doc.documentElement.setAttribute("data-js-focus-visible", "");
    doc.documentElement.setAttribute("data-turbo-loaded", "");
    const base = doc.createElement("base");
    base.href = url;
    doc.head.prepend(base);
    const policy = doc.createElement("meta");
    policy.httpEquiv = "Content-Security-Policy";
    policy.content = "script-src 'none'; object-src 'none'; frame-src 'none'";
    doc.head.prepend(policy);
    return `<!doctype html>\n${doc.documentElement.outerHTML}`;
  }, {original, theme, url});
  await page.route(url, (route) => route.fulfill({contentType: "text/html", body: restored}));
  await page.goto(url, {waitUntil: "networkidle"});
  await page.evaluate(() => document.fonts.ready);
  const before = await page.screenshot({fullPage: true, animations: "disabled"});
  const html = await archivePage(page);
  if (unsafeRequests.length) throw new Error("Recovery violated the read-only boundary");
  const offline = await browser.newContext({viewport: {width: 1280, height: 720}, offline: true, colorScheme: theme as "light" | "dark", reducedMotion: "reduce", locale: "en-US", timezoneId: "UTC"});
  const saved = await offline.newPage();
  const requests: string[] = [];
  saved.on("request", (request) => {if (/^https?:/.test(request.url())) requests.push(request.url());});
  await saved.setContent(html, {waitUntil: "load"});
  await saved.evaluate(() => document.fonts.ready);
  const audit = await saved.evaluate(() => ({
    background: getComputedStyle(document.body).backgroundColor,
    font: getComputedStyle(document.body).fontFamily,
    images: document.images.length,
    brokenImages: Array.from(document.images).filter((image) => !image.complete || !image.naturalWidth).length,
    scripts: document.scripts.length,
  }));
  const png = await saved.screenshot({fullPage: true, animations: "disabled"});
  if (requests.length || audit.brokenImages || audit.scripts) throw new Error(`Offline archive failed: ${JSON.stringify({requests, audit})}`);
  await writeFile(output, html, {flag: "wx"});
  await writeFile(`${output}.png`, png, {flag: "wx"});
  await writeFile(`${output}.online.png`, before, {flag: "wx"});
  const report = {
    kind: "recovered-html-derivative", recoveredAt: new Date().toISOString(),
    source: resolve(input), sourceSha256: sha256(original), output: resolve(output), sha256: sha256(html),
    theme, url, ...audit, networkRequests: requests.length,
    restoredOnlinePngSha256: sha256(before), offlinePngSha256: sha256(png),
    restoredOnlinePixelsMatchOffline: before.equals(png),
    limitations: "Root attributes reconstructed from the observed GitHub document and PNG theme; assets fetched at recovery time. Uncaptured shadow content (including relative timestamps) cannot be recovered. Original evidence remains authoritative.",
  };
  await writeFile(`${output}.json`, JSON.stringify(report, null, 2) + "\n", {flag: "wx"});
  if (!before.equals(png)) throw new Error(`Offline pixels differ; inspect ${output}.json and its PNGs`);
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
