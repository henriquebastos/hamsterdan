# V5 inline effect crash recovery completed

CV17.DS3.1 proved restart convergence for the four V5 inline-effect Activities:
review-agent execution, findings publication, rerun issuance, and mutation.
Canonical Petrus History freezes each exact work value, globally scoped
operation, and one-attempt policy. An unresolved occurrence redispatches after
restart; Agenticus, comment, rerun, and git ledgers reconcile lookup-first so a
landed effect with a lost Activity terminal is not repeated. Unknown failures
remain loud.

Review recovery now freezes the exact credential-free `ReviewRequest` in
host-owned SQLite custody before first Agenticus submission. Replays load and
validate that digest-protected snapshot before any fresh provider context read,
preventing changed comments or check evidence from causing an Agenticus
operation conflict. Ledger-specific bounded identity validation rejects
whitespace, controls, non-ASCII text, oversized values, and marker-incompatible
comment operations before dispatch.

The restart portfolio covers pre-effect and post-effect cuts, repeated restart,
provider movement, unreadable review context, exact request and Activity
identity, and operation/digest conflicts. All V5 topology tests passed (236),
the affected host and Agenticus portfolio passed, and `scripts/check full`
passed with 1,046 Python tests, nine Bun relay tests, formatting, Ruff, typing,
and source/wheel builds. Oracle boundary review traced both prior blockers and
the complete replay path, then returned `clear to commit`. CV17.DS3 remains
active for the remaining timer, custody, runnable-index, and selected-host
restart portfolio.
