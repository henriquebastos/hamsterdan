# Staleness Check

Re-reading the pull request immediately before any GitHub write to confirm it is still open, on the same head commit, same base branch, and same settings the queued request assumed. If anything changed, the write is skipped.

- Use when: the last-second re-read guarding one GitHub write.
- Do not use for: evaluating requirements; readiness is decided by the workflow, not here.
- Avoid: authority, current authority, authority fencing, fence, claim.
- Related: [Activity](activity.md), [Generation](generation.md)
