import {mkdir, readFile, writeFile} from "node:fs/promises";
import {join, resolve} from "node:path";
import {chromium} from "playwright";
import {pngDimensions} from "./png";
import {sha256} from "./render";
import {verifyDigest} from "./proof-demo";

const root = resolve(import.meta.dir, "../../..");
const sourceManifest = "docs/project/roadmap/cv19-private-v0-1-production/proof/pr83-html-recovery-manifest.json";
const manifestBytes = await readFile(join(root, sourceManifest));
const recovery = JSON.parse(manifestBytes.toString());
const output = "tools/demo-video/output/proof/pr83-dark";
await mkdir(join(root, output, "pr83"), {recursive: true});
const browser = await chromium.launch();
const pages = [];
try {
  for (const source of recovery.pages) {
    const original = await readFile(join(root, source.output), "utf8");
    verifyDigest(Buffer.from(original), source.sha256, source.output);
    if (!original.startsWith('<!doctype html>\n<html lang="en" data-color-mode="auto"')) throw new Error("Unexpected recovered root");
    const html = original.replace('data-color-mode="auto"', 'data-color-mode="dark"');
    const screenshots: Buffer[] = [];
    let audit;
    for (const colorScheme of ["light", "dark"] as const) {
      const context = await browser.newContext({viewport: {width: 1280, height: 720}, offline: true, colorScheme, reducedMotion: "reduce", locale: "en-US", timezoneId: "UTC"});
      const page = await context.newPage();
      const requests: string[] = [];
      page.on("request", (request) => {if (/^https?:/.test(request.url())) requests.push(request.url());});
      await page.setContent(html, {waitUntil: "load"});
      await page.evaluate(() => document.fonts.ready);
      audit = await page.evaluate(() => ({
        background: getComputedStyle(document.body).backgroundColor,
        foreground: getComputedStyle(document.body).color,
        height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
        scripts: document.scripts.length,
        brokenImages: Array.from(document.images).filter((image) => !image.complete || !image.naturalWidth).length,
        signInBanners: document.querySelectorAll('[data-test-selector="comments-sign-in-link"]').length,
      }));
      if (requests.length || audit.background !== "rgb(13, 17, 23)" || audit.foreground !== "rgb(240, 246, 252)" || audit.scripts || audit.brokenImages || audit.signInBanners) throw new Error(`Dark offline audit failed: ${source.output}`);
      const png = await page.screenshot({fullPage: true, animations: "disabled"});
      const dimensions = pngDimensions(png);
      if (dimensions.width !== 1280 || dimensions.height !== audit.height) throw new Error("Screenshot height mismatch");
      screenshots.push(png);
      await context.close();
    }
    if (!screenshots[0].equals(screenshots[1])) throw new Error("Browser preference changes the dark presentation");
    const file = join(output, "pr83", source.output.split("/").at(-1));
    await writeFile(join(root, file), html);
    await writeFile(join(root, `${file}.png`), screenshots[0]);
    pages.push({source: source.output, sourceSha256: source.sha256, output: file, sha256: sha256(html), offlinePngSha256: sha256(screenshots[0]), theme: "dark", networkRequests: 0, preferencePixelsMatch: true, ...audit});
    console.log(`Verified dark: ${file}`);
  }
} finally {
  await browser.close();
}
const index = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PR83 · Dark proof views</title><style>html{color-scheme:dark}body{background:#0d1117;color:#f0f6fc;font:16px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:24px}a{color:#58a6ff}li{margin:12px 0}</style><h1>PR83 · Dark proof views</h1><p>All 21 recovered pages use dark mode, independent of browser preference. Saved content is unchanged; the sign-in banner remains removed. Assets and root attributes were recovered after the proof; absolute dates replace unavailable relative timestamps.</p><ol>${pages.map((page) => `<li><a href="pr83/${page.output.split("/").at(-1)}">${page.output.split("/").at(-1)}</a> · <a href="pr83/${page.output.split("/").at(-1)}.png">Screenshot</a></li>`).join("")}</ol></html>`;
await writeFile(join(root, output, "index.html"), index);
const manifest = {schema: 1, kind: "dark-recovered-html-derivatives", pull_request: 83, sourceManifest: {path: sourceManifest, sha256: sha256(manifestBytes)}, renderer: {path: "tools/demo-video/live/pr83-dark.ts", sha256: sha256(await readFile(import.meta.path))}, index: {path: join(output, "index.html"), sha256: sha256(index)}, presentationEdits: ["Set only the recovered HTML root data-color-mode from auto to dark. Original source content and embedded assets unchanged."], pages};
await writeFile(join(root, "docs/project/roadmap/cv19-private-v0-1-production/proof/pr83-dark-manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
