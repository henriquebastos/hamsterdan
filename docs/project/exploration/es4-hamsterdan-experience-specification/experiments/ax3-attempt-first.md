# AX3 — Attempt-first gates: the operation is the fence

## Question

Navigator doctrine: *don't pre-check authority — just do the operation;
it fails if things changed, and we classify, discard, and wait for the
webhook.* Does this hold against real provider semantics, and does it
simplify the subnets?

Spike: [ax3-attempt-first/](ax3-attempt-first/) — 7 tests, all passing;
ES-003 primitives unchanged.

## Verified provider facts (the question "how will GitHub handle this?")

| Effect | Provider semantics | Source |
| --- | --- | --- |
| Git ref advance | Production uses GraphQL **exact compare-and-swap** with `expected_head`; a moved branch rejects — no force, no overwrite. REST non-force is fast-forward-only, which rejects on concurrent movement by parentage. | `src/hamsterdan/host/git_publish.py:249-258`; docs.github.com git/refs |
| PR review comment | A `commit_id` that is no longer head is **accepted** and merely rendered *outdated* in the UI ("Not using the latest commit SHA may render your review comment outdated"). | docs.github.com rest/pulls |
| Issue comment | No head/commit binding at all — always lands on an open conversation. | docs.github.com rest/issues |

So the two gates split:

```text
GIT GATE      provider-atomic. The CAS closes the race COMPLETELY.
              A pre-check adds no correctness — the operation is the fence.
COMMENT GATE  provider-unfenced. A stale comment CANNOT fail — it lands.
              No pre-check can close the race either: production's own
              fence (effects.py:89-146) re-reads the PR immediately
              before POST and still leaves a milliseconds window.
              Toleration + supersession is mandatory in EVERY design.
```

Which means: authority pre-checks are never correctness anywhere. At the
git gate they are redundant; at the comment gate they are insufficient.
They are at most **economy** (don't dispatch provably-stale work, don't
post noise) — an optimization the control layer may apply, not subnet
structure.

## Before/after: the fence transition disappears

```python
# AX2 (fenced style) — 5 transitions, authority context, read arc:
interior = rail_then(rail_then(prepare_basis(), run_agent(w)), draft_publication())
fenced   = then(interior, fence_authority(), on="out")      # reads 'authority'
subnet   = then(fenced, publish_findings(w), on="current")

# AX3 (attempt-first) — 3 transitions, ZERO contexts:
interior = rail_then(prepare_change(), agent_patch(w))
subnet   = then(interior, commit_gate(w), on="out")         # the gate classifies itself
```

```text
              transitions  contexts  read arcs  stale handling
AX2 fenced         5          1          1      fence transition → 'stale' exit
AX3 attempt-first  3          0          0      gate outcome     → 'moved' exit
```

Shape M becomes **context-free**: entry → prepare → agent → CAS gate →
exits, nothing ambient. The staleness signal moved from a dedicated
fence transition into the gate's own outcome classification:

```python
outcomes={"committed": "ProvisionalHead",   # → control verifies the head
          "moved":     "BranchMoved",       # kind-2: preconditions changed — NOT an error
          "fault":     "NonrecoverableFault"}
```

## Executed evidence

```text
moved branch    → agent ran (money spent), CAS rejected, branch
                  untouched by us, exit moved {expected: h1, actual:
                  h2-someone-pushed} — discard-and-wait-for-webhook,
                  exactly the doctrine
kind-1 replay   → trailers match → committed {reused: True}; the WORK
                  reran (agent_runs == 2), the WORLD effect did not
trailer clash   → same operation, different digest → fault
stale comment   → landed, outdated: true, marker carries its own head
                  (self-identifying for supersession) — GitHub cannot
                  reject it, and we don't pretend otherwise
```

## The correction to AX1

AX1's shape M drew `fence(authority)` before agent work and before the
gate (mirroring production `activities.py:471-483`). Reclassified:

```text
was:  fence(authority) → agent → validate → git_gate   # fence = correctness
now:  [economy check]  → agent → validate → git_gate   # gate = correctness
       optional, control-layer                          # CAS = the fence
```

The same applies to the review subnet's entry: the agent needs no
authority to *work* — only the gate decides. AX2's `fence_authority`
step before `publish_findings` is likewise economy (cheap local check
against durable authority, no provider read), tuning noise vs cost:

```text
level 0  no check         simplest; stale comments land as outdated noise
level 1  local check      free (durable authority, no provider read);
                          catches everything the instance already knows
level 2  provider re-read production today; ms-window remains anyway
```

All three need supersession downstream, so the choice never affects
correctness — pick per gate by noise economics. (A stale *outdated*
finding comment is arguably even informative; a stale readiness
advisory is not — levels may differ per publication kind.)

## Conclusion

**Promising; continue — with AX1 amended.** Attempt-first is not just
viable; at the git gate it is what production already does, minus the
redundant ceremony. Shape M drops from 5 transitions + 1 context to 3
transitions + 0 contexts. The residual design freedom (economy levels
at comment gates) is now an explicit dial, not hidden correctness.
AX4 composes two subnets through typed ports — including the
`committed → provisional head → verified admission` loop back through
the control layer, which is where attempt-first hands responsibility.
[AX6](ax6-unified-quiescence.md) took that handoff first: the loop
collapses into `Quiescent(expected=head)` — quiesce on commit, resume
`confirmed` when ingress observes the expected head.
