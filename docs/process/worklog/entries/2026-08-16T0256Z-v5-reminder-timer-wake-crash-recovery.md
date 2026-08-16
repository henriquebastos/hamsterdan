# V5 reminder and timer-wake crash recovery completed

CV17.DS3.2 proved restart convergence for reminder publication and its
host-owned wake path. Reminder Activities now freeze the immutable
`reminder:{timer_id}` provider marker under a one-attempt policy. A replayed
unresolved occurrence performs marker lookup before authority and recipient
reads, so a landed reminder with a lost Activity terminal is not posted twice.

The selected-V5 HostService crash test matures one reminder, publishes it,
rearms the actor loop, and commits those typed facts to Petrus History, then
simulates process death before the disposable runnable hint is replaced. After
removing both timer and runnable SQLite projections, startup rebuilds the next
deadline from canonical History, posts nothing early, and publishes exactly
once when that reconstructed deadline matures.

The focused recovery, timer, runnable, and host portfolio passed with 178
tests. `scripts/check full` passed with 1,054 Python tests, nine Bun relay
tests, formatting, Ruff, typing, and source/wheel builds. Oracle traced the
inline replay and projection-rebuild paths, then returned `clear to commit`.
