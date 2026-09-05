// SingleFile owns CSS parsing, nested resource embedding and rendered DOM serialization.
// @ts-expect-error single-file-core ships JavaScript without declarations.
import {getPageData} from "single-file-core/single-file.js";
// @ts-expect-error single-file-core ships JavaScript without declarations.
import * as cssTree from "single-file-core/vendor/css-tree.js";

Object.assign(globalThis, {
  archiveRenderedPage: async () => {
    const failures = new Set<string>();
    const result = await getPageData({
      removeHiddenElements: false,
      removeUnusedStyles: true,
      removeUnusedFonts: true,
      removeAlternativeFonts: true,
      removeAlternativeImages: true,
      removeAlternativeMedias: true,
      removeFrames: true,
      blockScripts: true,
      blockVideos: true,
      blockAudios: true,
      insertMetaCSP: true,
      insertSingleFileComment: true,
      saveFavicon: false,
      loadDeferredImages: false,
      compressHTML: false,
    }, {
      fetch: async (url: string) => {
        try {
          const response = await fetch(url, {credentials: "omit"});
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response;
        } catch (error) {
          failures.add(new URL(url, location.href).pathname);
          throw error;
        }
      },
    });
    if (failures.size) throw new Error(`Archive resources unavailable: ${[...failures].join(", ")}`);
    const doc = new DOMParser().parseFromString(result.content, "text/html");
    // A captured automatic theme must survive opening the file on a machine
    // whose preferred theme differs from the capture browser's.
    doc.querySelectorAll("style").forEach((style) => {
      let css = style.textContent ?? "";
      const replacements: {start: number; end: number; text: string}[] = [];
      cssTree.walk(cssTree.parse(css, {positions: true}), (node: {type: string; name?: string; prelude?: {loc: {start: {offset: number}; end: {offset: number}}}}) => {
        if (node.type !== "Atrule" || node.name !== "media" || !node.prelude) return;
        const {start, end} = node.prelude.loc;
        const condition = css.slice(start.offset, end.offset);
        if (condition.includes("prefers-color-scheme")) {
          replacements.push({start: start.offset, end: end.offset, text: matchMedia(condition).matches ? "all" : "not all"});
        }
      });
      // Replace only media conditions: CSSOM serialization can corrupt border
      // shorthands containing variables when a later longhand overrides them.
      for (const replacement of replacements.sort((a, b) => b.start - a.start)) {
        css = css.slice(0, replacement.start) + replacement.text + css.slice(replacement.end);
      }
      style.textContent = css;
      if (style.media.includes("prefers-color-scheme")) style.media = matchMedia(style.media).matches ? "all" : "not all";
    });
    return `<!doctype html>\n${doc.documentElement.outerHTML}`;
  },
});
