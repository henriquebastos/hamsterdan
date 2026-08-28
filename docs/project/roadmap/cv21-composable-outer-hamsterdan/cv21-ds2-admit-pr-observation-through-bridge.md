---
code: CV21.DS2
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV21.DS1 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv21-ds1-first-bridged-pr-lifecycle.md
  - contract-inheritance.md
  - ../../decisions/records/2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md
---

# CV21.DS2 — Admit one PR observation through the bridge

## Outcome

Accept one signed GitHub webhook through new provider normalization and durable
host delivery custody, then acknowledge the HTTP request without waiting for
readiness. A later authority turn performs source-neutral readiness admission,
bridge conversion, and identified Petrus History delivery until the current
Net folds the exact observation. Custodied, acknowledged, admitted, and folded
remain distinct reconstructible cuts.

## Vertical path

```text
HTTP request: raw webhook -> new GitHub verification/normalization
  -> host delivery custody -> HTTP acknowledgement -> request ends

later authority turn: PullRequestSnapshot + provenance -> focused observation/key
  -> manifest/grant -> bridge conversion -> identified History -> current fold
  -> detached posture -> host delivery completion
```

## Owns

- first provider models, webhook acquisition, route evidence, and durable host
  delivery custody;
- snapshot/provenance, focused observation/key, ingress manifest/grant/entries,
  exact classification, and acknowledgement cuts; and
- first observation-family bridge census and correspondence scenarios.

## Excludes

No provider exact read, discovery, successor incarnation/currentness, effect,
new workflow fold, or second admission ledger.

## Acceptance

- exact duplicate, corroboration, collision, incomparable evidence, and refusal
  have closed finite outcomes;
- the HTTP response requires only durable host custody and never waits for a
  readiness fold, Dispatch claim, provider effect, or Worker;
- History is the sole workflow-admission ledger;
- same accepted input reaches the current Net exactly once across every named
  crash cut without old value leakage;
- bridge conversion does not add policy or provider provenance to semantic
  equality; and
- owner-local/root replay and mutation-sensitive checks prove the full path.
