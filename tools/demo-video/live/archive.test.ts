import {expect, test} from "bun:test";
import {readFile} from "node:fs/promises";
import {createRequire} from "node:module";
import {dirname, join} from "node:path";
import {chromium} from "playwright";
import {archivePage} from "./archive";

test("a saved page retains its theme, nested assets and rendered shadow content without networking", async () => {
  const browser = await chromium.launch();
  try {
    const font = await readFile(join(dirname(createRequire(import.meta.url).resolve("playwright-core/package.json")), "lib/vite/recorder/assets/codicon-DCmgc-ay.ttf"));
    const context = await browser.newContext({viewport: {width: 600, height: 400}, colorScheme: "dark"});
    await context.route("https://example.test/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/font.ttf") {
        await route.fulfill({contentType: "font/ttf", body: font});
        return;
      }
      const resources: Record<string, [string, string]> = {
        "/": ["text/html", `<!doctype html><html lang="en" data-theme="dark"><head>
          <link rel="stylesheet" href="/main.css"></head><body><h1>Saved review</h1>
          <img src="/icon.svg" width="40" height="40"><b class="icon">&#xea60;</b><relative-time>wrong fallback</relative-time>
          <script>document.querySelector('relative-time').attachShadow({mode:'open'}).innerHTML='<span>5 minutes ago</span>';</script>
          </body></html>`],
        "/main.css": ["text/css", '@import url("nested.css"); html[data-theme="dark"] body {background:#0d1117;color:white;margin:20px;--thin:1px} h1{border:var(--thin) solid orange;border-bottom:0} @media(prefers-color-scheme:dark){body{border:3px solid orange}}'],
        "/nested.css": ["text/css", '@font-face{font-family:Fixture;src:url("font.ttf")} .icon{font-family:Fixture} h1 {color:rgb(123,200,42);background-image:url("icon.svg");padding-left:50px}'],
        "/icon.svg": ["image/svg+xml", '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" fill="orange"/></svg>'],
      };
      const resource = resources[path];
      if (!resource) throw new Error(`unexpected fixture resource ${path}`);
      await route.fulfill({contentType: resource[0], body: resource[1]});
    });
    const live = await context.newPage();
    await live.goto("https://example.test/");
    await live.evaluate(() => document.fonts.ready);
    const before = await live.screenshot();
    const html = await archivePage(live);
    expect((await live.screenshot()).equals(before)).toBeTrue();
    const offline = await browser.newContext({viewport: {width: 600, height: 400}, colorScheme: "light", offline: true});
    const saved = await offline.newPage();
    const requests: string[] = [];
    saved.on("request", (request) => {if (/^https?:/.test(request.url())) requests.push(request.url());});
    await saved.setContent(html, {waitUntil: "load"});
    await saved.evaluate(() => document.fonts.ready);
    expect(await saved.locator("body").evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(13, 17, 23)");
    expect(await saved.locator("img").evaluate((el: HTMLImageElement) => el.naturalWidth)).toBe(40);
    expect(await saved.locator("relative-time span").innerText()).toBe("5 minutes ago");
    expect(await saved.evaluate(() => document.fonts.check("16px Fixture", "\uea60"))).toBeTrue();
    expect((await saved.screenshot()).equals(before)).toBeTrue();
    expect(requests).toEqual([]);
    expect(await saved.locator("script").count()).toBe(0);
  } finally {
    await browser.close();
  }
}, 30_000);

test("missing visible resources stop capture instead of producing a plausible but incomplete archive", async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.route("https://example.test/**", (route) => route.fulfill({status: 404, body: "missing"}));
    await page.setContent('<html><body><img src="https://example.test/missing.png"></body></html>');
    const result = await archivePage(page).catch((error: Error) => error);
    expect(result).toBeInstanceOf(Error);
    expect(String(result)).toContain("Archive resources unavailable: /missing.png");
  } finally {
    await browser.close();
  }
});
