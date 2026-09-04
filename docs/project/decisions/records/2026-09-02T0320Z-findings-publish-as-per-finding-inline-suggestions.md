---
status: Decided
raised: 2026-09-02
decided: 2026-09-02
recorded: 2026-09-02T0320Z
deciders:
  - Henrique (Navigator)
related:
  - 2026-09-01T2057Z-pr-monitoring-narrows-to-watched-authors.md
---

# Findings publish as per-finding inline suggestions

## Decision

Each review finding is its own native review comment anchored to the
finding's primary changed line in **Files changed**, carrying a GitHub
```suggestion``` block whenever a concrete replacement exists. A
multi-location finding stays one comment at its primary anchor and
links its related locations. The single "Hamsterdan review findings"
batch comment in **Conversation** is superseded as the primary
presentation; it remains only as the fail-closed fallback when GitHub
definitively rejects an anchor.

Finding content is written for human attention and low cognitive load:
lead with what is wrong and what to do, in prose. The internal finding
structure — IDs, severity labels, "Evidence:"/"Primary location:"
scaffolding — never renders to the reader; identity lives in the
machine marker, and blocking status is the summary board's job.

## Rationale

The Navigator reviewed the first production findings batch (PR #63,
2026-09-02) and ruled the expectation: findings belong on the lines
they are about, one comment each, using GitHub's native suggestion
affordance so the author can apply a fix in one click. A single batch
comment forces the reader to map references to code themselves, and
exposing the finding data structure taxes attention that the content
should be earning. The qualification-era production topology already
rendered three native comments for the hero fixture; V5's batch
presentation regressed that reader experience.

## Consequences

- The V5 findings publication seam moves from one immutable batch
  operation to per-finding anchored review comments, keeping
  lookup-first identity and exact-head fencing per finding.
- A transient HTTP rejection consumes the inline publisher's one bounded
  retry only after lookup proves the finding absent; the retry receives a
  fresh exact-head fence. Structured payload and authorization failures do
  not retry.
- Anchor rejection falls back to one immutable conversation comment,
  never disguised as success; authorization failures still fail closed.
- Native review comments create resolvable threads, so human review
  thread gates begin to interact with Dan's findings. Ruled 2026-09-02:
  the summary board's unresolved-thread count **excludes** Dan's own
  threads — the Dan's-review row already carries the finding signal,
  and counting the same problem twice would nag the reader for one
  fact. Dan auto-resolves each thread whose finding a new head fixed,
  so rulesets that require thread resolution before merge stay
  consistent with an all-clear board.
