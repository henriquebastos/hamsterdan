---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-008 — Establish one Actions-assessment owner

## Existing field refined

Provider reconciliation and the durable Actions-discovery Activity independently
selected the exact workflow run, attached required jobs, interpreted the run
result, and selected failed required jobs. The copies had already diverged:
reconciliation normalized provider `pending` into `queued` or `in_progress`,
while Activity discovery attempted to construct a strict `ActionsObservation`
with the unsupported value `pending`.

An unused `VerifiedSnapshot` aggregate also grouped pull-request, policy, and
human-review reads without an owning production consumer.

## Accepted boundary

Exact-run selection remains an explicit provider read because the durable
Activity deliberately establishes run presence before fetching branch policy.
`GitHubAuthority.actions_evidence` then owns assessment of that selected run:

```python
@dataclass(frozen=True)
class ActionsEvidence:
    run: ActionsRunSnapshot
    conclusion: Literal["queued", "in_progress", "success", "failure"]
    failed_required_jobs: tuple[tuple[str, str | None], ...]

def actions_evidence(
    self,
    run: ActionsRunSnapshot,
    required_checks: Sequence[str],
) -> ActionsEvidence: ...
```

The provider attaches required jobs, derives the provider result, normalizes
pending run state, rejects unsupported terminal conclusions, and returns sorted
failed-job evidence. Reconciliation still owns observation identity and current
workflow context. The Activity still owns fresh authority fencing and its typed
domain result. Rerun brokerage retains exact lookup-first operation ownership.

`VerifiedSnapshot` and `verified_snapshot()` were deleted without replacement.

## Validation and review

The focused provider and host portfolio passed 194 tests. `scripts/check quick`
passed static, formatting, and production type checks. `scripts/check full`
passed static/type/format/package and relay gates, then 577 Python tests with one
explicitly external route deselected. Independent adversarial review returned
`APPROVE` with no release blocker.

## Consequences

- GitHub Actions assessment now has one provider owner and one typed result.
- Reconciliation and durable discovery cannot drift on pending normalization or
  failed required-job selection.
- Absence still short-circuits before the Activity's policy read; provider call
  ordering and failure semantics are preserved.
- No broad provider snapshot, consumer-mode flag, workflow context, operation
  identity, authority fence, or Net concept entered `github_app`.
- No Net, lifecycle, Activity execution, scheduler, storage, or Petrus behavior
  changed. The Net remains 46 places, 69 transitions, 309 arcs, and 17
  retirements.
