# Exact-head bounded Actions inventory qualified locally

Fresh selected-V5
[`HBNetwork/demo-pr-readiness` PR 53](https://github.com/HBNetwork/demo-pr-readiness/pull/53)
at head `a0d711448ffa33b2b711fa278ce4a5c1d27e288f` crossed a repository-history
threshold: Actions run `31982201595` attempt 1 succeeded, but the host's
workflow inventory exceeded its deliberate 1 MiB response bound before any
manifest, agent call, or App effect. Direct App diagnostics proved the PR,
policy, base comparison, and human review reads; only the unfiltered 100-run
workflow page failed closed.

The provider boundary now requests the already-required exact head SHA and 20
runs per page. It still requires complete count-consistent, cycle-bounded
pagination and strict workflow, event, PR, and run evidence. All attempts for
the head remain visible, while the response limit and rerun evidence cuts are
unchanged. The App registration now validates with the native review-thread
event, and isolated role sessions prove `henriquebastos` as author and
`crisbastos` as reviewer.

Focused GitHub/provider and topology-parity checks passed 94 tests. The full
checkpoint passed 1,133 Python tests, nine Bun relay tests, Ruff, formatting,
typing, and source/wheel builds. A direct real-App read through the correction
returned exactly run `31982201595` attempt 1 with `success`. Oracle review found
no blocker and returned `clear to commit`. PR 53 remains normal custodied
failure evidence until deployment resumes its exact delivery.
