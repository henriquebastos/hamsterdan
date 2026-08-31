---
code: CV21.DS10
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV21.DS9 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv21-ds9-fence-lifecycle-authority.md
  - ../../decisions/records/2026-08-28T0153Z-configured-repository-recovery-discovers-unknown-open-pull-requests.md
---

# CV21.DS10 — Discover unregistered open PRs boundedly

## Outcome

Repeated bounded discovery passes over operator-configured repositories find an
eligible open PR absent from durable host registration, exact-read it, and
idempotently register/enqueue it through the same DS9 admission path. No pass
claims an atomic repository snapshot.

## Vertical path

```text
configured repository -> bounded list page/pass custody -> unknown candidate
  -> exact provider read -> classify -> idempotent register/enqueue
  -> common admission -> bridge-mounted retained Net -> detached posture
```

## Owns

- configured-repository discovery-pass and explicit pass-boundary custody;
- bounded list-page continuation/rate behavior and candidate classification;
- exact-read-before-registration and idempotent registration/enqueue; and
- discovery simulation, quiescence/fairness assumptions, resources, and provider
  correspondence.

## Excludes

No repository authorization inferred from accessibility, list-row workflow
evidence, atomic-snapshot claim, cross-repository scan, or new workflow family.

## Acceptance

- only configured repositories are listed;
- list summaries remain hints and never enter History;
- exact read proves the candidate before durable subject creation;
- restarts resume bounded pass custody without skipping or double-registering;
- repeated passes eventually register a stable eligible PR under stated
  availability/rate/quiescence assumptions; and
- page, pass, candidate, and portfolio resources are measured and bounded.
