import type {Page} from "playwright";

let bundle: Promise<string> | undefined;

export const archiveScript = (): Promise<string> => bundle ??= (async () => {
  const result = await Bun.build({entrypoints: [new URL("./archive-browser.ts", import.meta.url).pathname], target: "browser", format: "iife", define: {"import.meta.url": '"about:blank"'}});
  if (!result.success) throw new Error(`Cannot build HTML archiver: ${result.logs.join("; ")}`);
  return result.outputs[0].text();
})();

export const archivePage = async (page: Page): Promise<string> => {
  await page.evaluate(await archiveScript());
  return page.evaluate(() => (globalThis as unknown as {archiveRenderedPage: () => Promise<string>}).archiveRenderedPage());
};
