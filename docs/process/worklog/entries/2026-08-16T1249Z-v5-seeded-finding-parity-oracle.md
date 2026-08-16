# V5 seeded-review-finding parity oracle established

CV17.DS4.3 extends the real-host semantic harness with historical PR 26's
GitHub-visible meaning. Exact-head required CI is green while the coordinating
agent returns one validated high-severity blocking finding. Production and V5
each publish that finding exactly once under an App-owned marker and stable
operation, expose its identity, title, explanation, and evidence, keep one
blocked dashboard, and publish no readiness advisory. Both quiesce without a
coding or conversation agent, rerun, Git/ref mutation, or merge.

The first behavioral run passed production and failed V5 because V5's batch
comment displayed an absent legacy `note` while only its hidden digest bound
the complete validated agent result. The V5 provider gate now renders the
validated finding fields for a human while preserving canonical digest binding
and lookup-first batch identity. The test permits production's inline finding
and V5's PR comment because parity concerns the actionable GitHub behavior, not
presentation or implementation equality.

Boundary review found that the same operation must also accept a comment
published by the old renderer before a worker crash. The gate now supplies the
digest-bound old body as compatible content to both its initial lookup and its
post-fence lookup/write boundary. A real `CommentPublisher` regression proves
that a held old comment lands without a claim read, fence, or duplicate post.

The focused finding/gate and parity checks passed with 53 selected tests.
`scripts/check full` passed with 1,072 Python tests, nine Bun relay tests,
formatting, Ruff, typing, and source/wheel builds. Fresh selected-V5 live GitHub
demonstrations remain mandatory for CV17 acceptance.
