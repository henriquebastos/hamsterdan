import {describe, expect, test} from "bun:test";
import {readFile} from "node:fs/promises";
import {parseManifest, watchedPageUrl} from "./manifest";

const validManifest = () => ({
  schema: 1,
  slug: "pr61-v5-hero",
  repository: "HBNetwork/demo-pr-readiness",
  pullRequest: 61,
  expectedState: "open",
  expectedHead: "e3d11a8171dbbb4af910b7c199a5f240dfb2441e",
  viewport: {width: 1440, height: 900},
  actors: [
    {login: "henriquebastos", href: "/henriquebastos"},
    {login: "crisbastos", href: "/crisbastos"},
    {login: "hamster-dan", href: "/apps/hamster-dan"},
  ],
  checkpoints: [
    {
      id: "findings",
      kind: "issue-comment",
      target: "5312507139",
      url: "https://github.com/HBNetwork/demo-pr-readiness/pull/61#issuecomment-5312507139",
      actor: "hamster-dan",
      expectedText: ["Hamsterdan review findings", "Calculate lease duration in seconds"],
      focusText: "Hamsterdan review findings",
      holdSeconds: 5,
    },
    {
      id: "repair-commit",
      kind: "commit",
      target: "e3d11a8171dbbb4af910b7c199a5f240dfb2441e",
      url: "https://github.com/HBNetwork/demo-pr-readiness/commit/e3d11a8171dbbb4af910b7c199a5f240dfb2441e",
      actor: "hamster-dan",
      expectedText: ["Repair hero review findings"],
      focusText: "Repair hero review findings",
      holdSeconds: 4,
    },
  ],
});

describe("live capture manifest", () => {
  test("admits the committed PR61 acceptance manifest", async () => {
    const raw = JSON.parse(await readFile(new URL("./manifests/pr61-v5-hero.json", import.meta.url), "utf8"));
    expect(parseManifest(raw).checkpoints).toHaveLength(14);
  });

  test("admits the committed PR56 clean-green manifest", async () => {
    const raw = JSON.parse(await readFile(new URL("./manifests/pr56-v5-clean-green.json", import.meta.url), "utf8"));
    const parsed = parseManifest(raw);
    expect(parsed.slug).toBe("pr56-v5-clean-green");
    expect(parsed.checkpoints).toHaveLength(4);
  });

  test("admits the committed PR57 transient-CI manifest", async () => {
    const raw = JSON.parse(await readFile(new URL("./manifests/pr57-v5-transient-ci.json", import.meta.url), "utf8"));
    const parsed = parseManifest(raw);
    expect(parsed.slug).toBe("pr57-v5-transient-ci");
    expect(parsed.checkpoints.map(({kind}) => kind)).toEqual([
      "actions-attempt",
      "actions-attempt",
      "issue-comment",
      "issue-comment",
    ]);
  });

  test("admits the committed PR63 production hero manifest", async () => {
    const raw = JSON.parse(await readFile(new URL("./manifests/pr63-v6-hero.json", import.meta.url), "utf8"));
    const parsed = parseManifest(raw);
    expect(parsed.slug).toBe("pr63-v6-hero");
    expect(parsed.expectedState).toBe("closed");
    expect(parsed.checkpoints).toHaveLength(3);
  });

  test("carries no watch plan unless the manifest declares one", () => {
    expect(parseManifest(validManifest()).watch).toBeNull();
  });

  test("carries the watch cadence, duration, and caption a live journey needs", () => {
    const value = {...validManifest(), watch: {pollSeconds: 5, durationSeconds: 300, maxStates: 12, caption: "PR 61"}};
    expect(parseManifest(value).watch).toEqual({pollSeconds: 5, durationSeconds: 300, maxStates: 12, caption: "PR 61"});
  });

  test.each([
    ["unknown watch field", {pollSeconds: 5, durationSeconds: 300, maxStates: 12, caption: "PR 61", selector: "body"}],
    ["cadence longer than the duration", {pollSeconds: 300, durationSeconds: 5, maxStates: 12, caption: "PR 61"}],
    ["zero cadence", {pollSeconds: 0, durationSeconds: 300, maxStates: 12, caption: "PR 61"}],
    ["single-state ceiling", {pollSeconds: 5, durationSeconds: 300, maxStates: 1, caption: "PR 61"}],
    ["empty caption", {pollSeconds: 5, durationSeconds: 300, maxStates: 12, caption: ""}],
  ])("rejects a watch plan with %s", (_name, watch) => {
    expect(() => parseManifest({...validManifest(), watch})).toThrow();
  });

  test("derives the watched page URL from the repository and pull request", () => {
    expect(watchedPageUrl(parseManifest(validManifest()))).toBe("https://github.com/HBNetwork/demo-pr-readiness/pull/61");
  });

  test("accepts the closed public GitHub contract", () => {
    expect(parseManifest(validManifest()).slug).toBe("pr61-v5-hero");
  });

  test("carries the pull-request state the capture must observe", () => {
    for (const state of ["open", "closed", "merged"] as const) {
      expect(parseManifest({...validManifest(), expectedState: state}).expectedState).toBe(state);
    }
    expect(() => parseManifest({...validManifest(), expectedState: "draft"})).toThrow(/expectedState/);
  });

  test("accepts one exact GitHub Actions run attempt identity", () => {
    const value = validManifest();
    value.checkpoints[0] = {
      ...value.checkpoints[0],
      kind: "actions-attempt",
      target: "31990573431/attempts/1",
      url: "https://github.com/HBNetwork/demo-pr-readiness/actions/runs/31990573431/attempts/1",
    };
    expect(parseManifest(value).checkpoints[0].target).toBe("31990573431/attempts/1");
  });

  test("rejects a malformed GitHub Actions attempt identity", () => {
    const value = validManifest();
    value.checkpoints[0] = {
      ...value.checkpoints[0],
      kind: "actions-attempt",
      target: "31990573431/attempts/latest",
      url: "https://github.com/HBNetwork/demo-pr-readiness/actions/runs/31990573431/attempts/latest",
    };
    expect(() => parseManifest(value)).toThrow(/target/);
  });

  test.each([
    ["unknown top-level field", (value: any) => (value.cookie = "secret")],
    ["unknown checkpoint field", (value: any) => (value.checkpoints[0].selector = "body")],
    ["credential-bearing URL", (value: any) => (value.checkpoints[0].url = "https://token@github.com/x")],
    ["non-GitHub URL", (value: any) => (value.checkpoints[0].url = "https://example.com/evidence")],
    ["non-HTTPS URL", (value: any) => (value.checkpoints[0].url = "http://github.com/evidence")],
    ["wrong PR URL", (value: any) => (value.checkpoints[0].url = "https://github.com/HBNetwork/demo-pr-readiness/pull/60#issuecomment-5312507139")],
    ["unsafe output identity", (value: any) => (value.checkpoints[0].id = "../findings")],
    ["duplicate checkpoint", (value: any) => value.checkpoints.push({...value.checkpoints[0]})],
    ["malformed head", (value: any) => (value.expectedHead = "e3d11a8")],
    ["unbounded text", (value: any) => (value.checkpoints[0].expectedText = ["x".repeat(501)])],
    ["undeclared actor", (value: any) => (value.checkpoints[0].actor = "intruder")],
    ["focus outside assertions", (value: any) => (value.checkpoints[0].focusText = "not asserted")],
    ["invalid hold", (value: any) => (value.checkpoints[0].holdSeconds = 0)],
  ])("rejects %s", (_name, mutate) => {
    const value = validManifest();
    mutate(value);
    expect(() => parseManifest(value)).toThrow();
  });
});
