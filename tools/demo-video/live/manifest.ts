export type CheckpointKind = "issue-comment" | "review" | "commit" | "pr-checks" | "actions-run";

export type Actor = Readonly<{
  login: string;
  href: string;
}>;

export type Checkpoint = Readonly<{
  id: string;
  kind: CheckpointKind;
  target: string;
  url: string;
  actor: string;
  expectedText: readonly string[];
  focusText: string;
  holdSeconds: number;
}>;

export type CaptureManifest = Readonly<{
  schema: 1;
  slug: string;
  repository: string;
  pullRequest: number;
  expectedState: "open";
  expectedHead: string;
  viewport: Readonly<{width: number; height: number}>;
  actors: readonly Actor[];
  checkpoints: readonly Checkpoint[];
}>;

const EXACT_KEYS = {
  manifest: [
    "schema",
    "slug",
    "repository",
    "pullRequest",
    "expectedState",
    "expectedHead",
    "viewport",
    "actors",
    "checkpoints",
  ],
  viewport: ["width", "height"],
  actor: ["login", "href"],
  checkpoint: ["id", "kind", "target", "url", "actor", "expectedText", "focusText", "holdSeconds"],
} as const;

const requireRecord = (value: unknown, label: string): Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
};

const requireExactKeys = (value: Record<string, unknown>, keys: readonly string[], label: string) => {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${label} must contain exactly: ${keys.join(", ")}`);
  }
};

const requireString = (value: unknown, label: string, pattern: RegExp, maximum = 256): string => {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum || !pattern.test(value)) {
    throw new Error(`${label} is invalid`);
  }
  return value;
};

const requireInteger = (value: unknown, label: string, minimum: number, maximum: number): number => {
  if (!Number.isInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    throw new Error(`${label} is invalid`);
  }
  return value as number;
};

const publicGitHubUrl = (raw: unknown, label: string): URL => {
  if (typeof raw !== "string" || raw.length > 512) {
    throw new Error(`${label} is invalid`);
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`${label} is invalid`);
  }
  if (
    url.protocol !== "https:" ||
    url.hostname !== "github.com" ||
    url.port !== "" ||
    url.username !== "" ||
    url.password !== "" ||
    url.search !== ""
  ) {
    throw new Error(`${label} must be a credential-free public GitHub URL`);
  }
  return url;
};

const expectedCheckpointUrl = (
  repository: string,
  pullRequest: number,
  expectedHead: string,
  kind: CheckpointKind,
  target: string,
): string => {
  const root = `https://github.com/${repository}`;
  switch (kind) {
    case "issue-comment":
      return `${root}/pull/${pullRequest}#issuecomment-${target}`;
    case "review":
      return `${root}/pull/${pullRequest}#pullrequestreview-${target}`;
    case "commit":
      if (target !== expectedHead) {
        throw new Error("commit checkpoint must target the expected head");
      }
      return `${root}/commit/${target}`;
    case "pr-checks":
      return `${root}/pull/${pullRequest}/checks`;
    case "actions-run":
      return `${root}/actions/runs/${target}`;
  }
};

export const parseManifest = (raw: unknown): CaptureManifest => {
  const value = requireRecord(raw, "manifest");
  requireExactKeys(value, EXACT_KEYS.manifest, "manifest");
  if (value.schema !== 1 || value.expectedState !== "open") {
    throw new Error("unsupported live capture manifest");
  }

  const slug = requireString(value.slug, "slug", /^[a-z0-9]+(?:-[a-z0-9]+)*$/, 64);
  const repository = requireString(
    value.repository,
    "repository",
    /^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,38})\/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$/,
    140,
  );
  const pullRequest = requireInteger(value.pullRequest, "pullRequest", 1, 2_147_483_647);
  const expectedHead = requireString(value.expectedHead, "expectedHead", /^[0-9a-f]{40}$/, 40);

  const viewportValue = requireRecord(value.viewport, "viewport");
  requireExactKeys(viewportValue, EXACT_KEYS.viewport, "viewport");
  const viewport = {
    width: requireInteger(viewportValue.width, "viewport.width", 1280, 1920),
    height: requireInteger(viewportValue.height, "viewport.height", 720, 1080),
  };

  if (!Array.isArray(value.actors) || value.actors.length < 1 || value.actors.length > 8) {
    throw new Error("actors is invalid");
  }
  const actors = value.actors.map((rawActor, index) => {
    const actor = requireRecord(rawActor, `actors[${index}]`);
    requireExactKeys(actor, EXACT_KEYS.actor, `actors[${index}]`);
    const login = requireString(actor.login, `actors[${index}].login`, /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/);
    const href = requireString(actor.href, `actors[${index}].href`, /^\/(?:apps\/)?[A-Za-z0-9-]+$/, 64);
    if (href !== `/${login}` && href !== `/apps/${login}`) {
      throw new Error(`actors[${index}].href does not identify its login`);
    }
    return {login, href};
  });
  const actorLogins = new Set(actors.map(({login}) => login));
  if (actorLogins.size !== actors.length) {
    throw new Error("actor logins must be unique");
  }

  if (!Array.isArray(value.checkpoints) || value.checkpoints.length < 1 || value.checkpoints.length > 32) {
    throw new Error("checkpoints is invalid");
  }
  const checkpoints = value.checkpoints.map((rawCheckpoint, index) => {
    const checkpoint = requireRecord(rawCheckpoint, `checkpoints[${index}]`);
    requireExactKeys(checkpoint, EXACT_KEYS.checkpoint, `checkpoints[${index}]`);
    const id = requireString(checkpoint.id, `checkpoints[${index}].id`, /^[a-z0-9]+(?:-[a-z0-9]+)*$/, 64);
    const kinds: readonly CheckpointKind[] = ["issue-comment", "review", "commit", "pr-checks", "actions-run"];
    if (typeof checkpoint.kind !== "string" || !kinds.includes(checkpoint.kind as CheckpointKind)) {
      throw new Error(`checkpoints[${index}].kind is invalid`);
    }
    const kind = checkpoint.kind as CheckpointKind;
    const targetPattern = kind === "commit" ? /^[0-9a-f]{40}$/ : /^[1-9][0-9]{0,19}$/;
    const target = requireString(checkpoint.target, `checkpoints[${index}].target`, targetPattern, 40);
    const url = publicGitHubUrl(checkpoint.url, `checkpoints[${index}].url`).toString();
    if (url !== expectedCheckpointUrl(repository, pullRequest, expectedHead, kind, target)) {
      throw new Error(`checkpoints[${index}].url does not match its target`);
    }
    const actor = requireString(checkpoint.actor, `checkpoints[${index}].actor`, /^[A-Za-z0-9-]+$/);
    if (!actorLogins.has(actor)) {
      throw new Error(`checkpoints[${index}].actor is undeclared`);
    }
    if (
      !Array.isArray(checkpoint.expectedText) ||
      checkpoint.expectedText.length < 1 ||
      checkpoint.expectedText.length > 8
    ) {
      throw new Error(`checkpoints[${index}].expectedText is invalid`);
    }
    const expectedText = checkpoint.expectedText.map((text, textIndex) =>
      requireString(text, `checkpoints[${index}].expectedText[${textIndex}]`, /^[\x20-\x7e\n]+$/, 500),
    );
    if (new Set(expectedText).size !== expectedText.length) {
      throw new Error(`checkpoints[${index}].expectedText must be unique`);
    }
    const focusText = requireString(checkpoint.focusText, `checkpoints[${index}].focusText`, /^[\x20-\x7e\n]+$/, 500);
    if (!expectedText.includes(focusText)) {
      throw new Error(`checkpoints[${index}].focusText must be asserted`);
    }
    return {
      id,
      kind,
      target,
      url,
      actor,
      expectedText,
      focusText,
      holdSeconds: requireInteger(checkpoint.holdSeconds, `checkpoints[${index}].holdSeconds`, 2, 15),
    };
  });
  if (new Set(checkpoints.map(({id}) => id)).size !== checkpoints.length) {
    throw new Error("checkpoint ids must be unique");
  }

  return {
    schema: 1,
    slug,
    repository,
    pullRequest,
    expectedState: "open",
    expectedHead,
    viewport,
    actors,
    checkpoints,
  };
};
