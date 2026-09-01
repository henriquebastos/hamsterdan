import {describe, expect, test} from "bun:test";
import {readFile} from "node:fs/promises";
import {resolve} from "node:path";

const repositoryRoot = resolve(import.meta.dir, "../../..");

describe("demo toolchain ownership", () => {
  test("local orb setup installs the locked demo prerequisites", async () => {
    const setup = await readFile(resolve(repositoryRoot, ".agents/setup"), "utf8");

    expect(setup).toContain('bash -s "bun-v1.3.10"');
    expect(setup).toContain("missing_media_tools+=(ffmpeg)");
    expect(setup).toContain("bun install --frozen-lockfile");
    expect(setup).toContain("bunx playwright install --with-deps chromium");
  });

  test("local full gate runs the deterministic demo checks", async () => {
    const check = await readFile(resolve(repositoryRoot, "scripts/check"), "utf8");

    expect(check).toContain("(cd tools/demo-video && bun run check)");
  });

  test("hosted CI runs only the apt-free Python profile", async () => {
    const workflow = await readFile(
      resolve(repositoryRoot, ".github/workflows/ci.yml"),
      "utf8",
    );

    expect(workflow).toContain("scripts/check tests");
    expect(workflow).not.toContain("scripts/check full");
    expect(workflow).not.toContain("setup-bun");
    expect(workflow).not.toContain("tools/demo-video");
    expect(workflow).not.toContain("bun install --frozen-lockfile");
    expect(workflow).not.toContain("playwright install");
    expect(workflow).not.toContain("ffmpeg");
  });
});
