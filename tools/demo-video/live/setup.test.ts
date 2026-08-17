import {describe, expect, test} from "bun:test";
import {readFile} from "node:fs/promises";
import {resolve} from "node:path";

const repositoryRoot = resolve(import.meta.dir, "../../..");

describe("live capture setup and CI", () => {
  test("installs the locked browser and runs the deterministic media checks", async () => {
    const [setup, workflow, check] = await Promise.all([
      readFile(resolve(repositoryRoot, ".agents/setup"), "utf8"),
      readFile(resolve(repositoryRoot, ".github/workflows/ci.yml"), "utf8"),
      readFile(resolve(repositoryRoot, "scripts/check"), "utf8"),
    ]);
    expect(setup).toContain("bunx playwright install --with-deps chromium");
    expect(workflow).toContain("bun install --frozen-lockfile");
    expect(workflow).toContain("bunx playwright install --with-deps chromium");
    expect(workflow).toContain("ffmpeg");
    expect(check).toContain("bun run check");
  });
});
