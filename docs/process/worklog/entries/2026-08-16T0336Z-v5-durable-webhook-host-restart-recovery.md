# V5 durable webhook host-restart recovery completed

CV17.DS3.3 closed the durable recovery story with the missing outer-host crash
cut. A real selected-V5 HostService now has evidence for process death after a
custodied webhook has committed its immutable ingress manifest, authority
grant, one Agenticus review terminal, Petrus History, and runnable posture, but
before webhook acknowledgement.

On fresh-host startup, the still-pending delivery replays from retained
custody. Changed provider head truth is never read, the original Agenticus
operation remains single-attempt, History gains no duplicate delivery or
synthetic reconciliation, the authority grant remains sourced from the
original webhook, and custody becomes terminal with zero retries and one timer
hint. Cleanup between the simulated processes also leaves canonical state
unchanged. Existing production code already satisfied these invariants, so the
slice adds integration evidence rather than speculative implementation.

The focused selected-host, ingress, and inline-recovery portfolio passed with
147 tests. `scripts/check full` passed with 1,055 Python tests, nine Bun relay
tests, formatting, Ruff, typing, and source/wheel builds. Oracle found one stale
root-roadmap status, verified its correction, and returned `clear to commit`.
CV17.DS3 is complete; DS4 parity evidence remains.
