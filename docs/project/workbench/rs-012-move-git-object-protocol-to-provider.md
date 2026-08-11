---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-012 — Move Git object protocol to the provider

## Existing field refined

`HostGitPublisher` owned both provider-neutral publication policy and GitHub's
blob, tree, and commit REST protocol. It constructed base64 payloads, selected
GitHub endpoints, parsed response status and SHA evidence, admitted agent
patches, proved a local tree, checked current PR authority, and authorized the
ref update in one class.

## Accepted boundary

`GitHubAuthority.create_tree(...) -> str` now owns blob/tree request encoding
and exact response proof. `GitHubAuthority.create_commit(...) -> str` owns the
commit request and proof. Each accepted response must be status `201` with one
lowercase 40-hex SHA; malformed proof raises a provider-specific,
coordinate-free `GitHubObjectWriteError`.

The two provider calls deliberately remain separate. `HostGitPublisher`
extracts and validates staged entries, asks GitHub to create the tree, compares
the proven tree with its locally authorized tree, and only then asks GitHub to
create the commit. The host still owns path/mode/patch admission, parents and
operation trailers, current PR authority, exact ref compare-and-swap, and
publication-category projection.

No workflow, Activity, Net, credential, or mutable runtime value enters the
provider object-write API. No aggregate result was needed; each phase returns
only its proven SHA.

## Validation and review

Focused GitHub gateway and publication evidence passed 86 tests.
`scripts/check quick` passed static, format, and production type checks.
`scripts/check full`
passed package and relay gates, then 597 Python tests with one explicitly
external route deselected. Adversarial review initially found that the first
one-shot extraction weakened the host's expected-tree gate by creating a commit
before comparison. The API was split at that authorization point, a no-commit
regression test was added, and final review returned `APPROVE`.

## Consequences

- GitHub object endpoint and response semantics have one provider owner.
- Host publication policy remains host-owned and executes in its original
  security-sensitive order.
- Unexpected GitHub tree evidence cannot authorize a commit or ref update.
- Transport unavailability remains distinct from malformed object-write proof.
- No Net, lifecycle, Motus, scheduler, storage schema, or Petrus behavior
  changed.
