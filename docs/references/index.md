# References

## Ariad provenance

- Vendored `using-ariad` package from <https://github.com/henriquebastos/ariad>
  at Git revision `b70aa8da18c19500c6d3c9c53d3eb9bf5b2f9e47` (`main`):
  package version `0.3.0`, method digest
  `c118e38da423a3b07de392e3000b864613e384540b6d5180cfac180426a5b323`,
  package digest
  `7302f17bec822017dfb00302d5ec0613652e859a8de17899ef81abbca28a873e`,
  copied complete from `skills/using-ariad` to
  `.agents/skills/using-ariad` on 2026-08-31. This version makes
  `docs/project/glossary/` the domain-language owner with the boundary
  entry form and adds the `method/domain-language` reference. Supersedes
  the 0.2.2 pin at `67eecc1c3fdd3ca7db313183a8c24662db3a1de8` (same day)
  and the 0.2.1 pin at `7521d53983039bd808051d34bdcc56faec3277da`
  (2026-08-09).

## Petrus provenance

- Engineering-convention and feedback-interface comparison:
  `henriquebastos/petrus@39eac9d39a8050541db2d4b11c12ab967f9492b9`,
  inspected from the sibling checkout on 2026-08-24. Hamsterdan adapted reusable
  boundary, durability, Activity, retry, testing, and command-interface practice;
  Petrus's internal package graph, exact structural rules, mutation targets,
  complexity baseline, and test seeds were not adopted as Hamsterdan policy.
  RS-029 later adopted compatible generic tool versions for ast-grep, mutmut,
  pytest-randomly, and pytest-xdist while defining Hamsterdan-owned rules,
  targets, seeds, and non-blocking audit semantics.
- Historical Petrus namespace migration and accepted application dependency:
  `henriquebastos/petrus@cd1187e44926d6a80e4a3538ad79762618d32a8b`,
  inspected 2026-08-01.
- Qualified workflow source: `examples/pr_readiness_next/` and
  `tests/examples/pr_readiness_next/` at that commit.
- Historical Petrus Agenticus adoption dependency:
  `henriquebastos/petrus@750c4321bb51563666ce43e88f753ebe1f068520`,
  inspected 2026-08-05.
- Accepted Petrus clean-root dependency baseline:
  `henriquebastos/petrus@116b0ddc460c0e04d4ad40c077158bd3498a4860`,
  inspected and accepted 2026-08-08. Hamsterdan consumes this exact Git revision
  historically and does not assume package publication.
- Accepted Motus Activity Execution V2 dependency:
  `henriquebastos/petrus@35d09023f40fac34dc84c54389466b669a79ec19`,
  implemented, fully validated, and accepted 2026-08-10. Hamsterdan consumes
  this exact Git revision for classified Activity failures, bounded retry
  policy, deadlines, and deterministic terminal-failure projection.
- Accepted shared-Worker Instance-scoped Activity dependency:
  `henriquebastos/petrus@cb9cb63c3938c9318a99c9f605a0364b3c81bd6b`,
  implemented, fully validated, and accepted 2026-08-10. This revision
  supersedes the V2 pin and adds first-class Worker execution Instance,
  optional host-composed scoped resolution, and bounded non-waiting Worker
  pumping without introducing a scheduler or serialized Activity scope.
- Accepted lifecycle-scope dependency:
  `henriquebastos/petrus@b0bb336a077b70b6d702aef26acbf8ad1381f9b3`,
  implemented, fully validated, and accepted 2026-08-11. Hamsterdan consumes
  this exact revision for durable `LifecycleScope` identity, canonical
  open/close/reset records, exact queue and Activity provenance, commit-first
  cancellation, restart repair, and deterministic late-terminal quarantine.
  This revision supersedes the shared-Worker pin without moving scheduling or
  provider custody into Petrus.
- Accepted custom typed-guard dependency:
  `henriquebastos/petrus@3b41f19aa68ed228e68324f7c6888371f805b560`,
  implemented, release-qualified, and accepted 2026-08-11. This revision
  supersedes the lifecycle-scope pin and adds only public
  `typed_guard(..., converter=...)` authoring over the existing typed guard
  plan. Ordinary guards and canonical Net, History, wire, runtime, handler, and
  Activity contracts remain unchanged.
- Accepted deterministic-simulation test-kit dependency:
  `henriquebastos/petrus@5ded726a339907175e5af6eb79cda9ab66816308`,
  inspected and pinned 2026-08-18. It supplies the pytest-independent supported
  `petrus.testing.dst/v3` defining module and `petrus-dst-world` artifact v3,
  while preserving strict v1/v2 artifact decode and replay. V3 adds seeded
  provenance; v2/v3 retain and exactly replay World-owned budget exhaustion and
  checker invariant failures through replay-result v2. Hamsterdan consumes only
  that public test surface; profile, checker, API, artifact, and replay-result
  compatibility remain separately pinned. Profile/runtime implementation
  exceptions remain harness failures rather than promoted counterexamples.
- Current resource-bounded deterministic-simulation dependency:
  `henriquebastos/petrus@44cac5ff48ac371ebae56323941983f30db13c0d`,
  inspected and pinned 2026-08-18. It supplies `petrus.testing.dst/v4` and
  `petrus-dst-world` artifact v4 with strict v1-v3 compatibility, exact
  deterministic profile-resource accounting, and the separately versioned
  `petrus.testing.dst.runner/v1` outer-process containment contract. A killed
  call yields an acknowledged prefix and unfinished attempt, never a fabricated
  replay artifact.
- Delivered CV21.DS2 phased-delivery prerequisite:
  `henriquebastos/petrus@4e5c2500af4eb439e8e8f5ec108982c81bfc7427`
  (`feat(engine): split identified delivery into durable phases`), verified at
  Petrus `origin/main` on 2026-08-30. It supplies the public bounded phased seam
  needed to distinguish identified acceptance from later fold and resume one
  accepted unfinished occurrence without private `Instance` access. The
  current Hamsterdan dependency remains intentionally pinned to
  `44cac5ff48ac371ebae56323941983f30db13c0d`; CV21.DS2 task 4 will update and
  qualify the pin when History acceptance first consumes the new seam.
- CV22 hierarchy evidence inspected 2026-08-28:
  `henriquebastos/petrus@2d26d34de9a1b34b7489ee2207f3492e777a282a`.
  Public `NetSpec` nested stamping flattens child paths into one built Net and
  rejects a stamped child's root-completion declaration. This proves reusable
  structural composition, not that an arbitrary child subnet is behaviorally
  equivalent to one abstract transition. CV22 must rule and prove any
  parent-first contract substitution separately.

## GitHub documentation

Authoritative GitHub documentation inspected 2026-08-01:

- <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app>
- <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/making-a-github-app-public-or-private>
- <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation>
- <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app>
- <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app>
- <https://docs.github.com/en/apps/maintaining-github-apps/modifying-a-github-app-registration>
- <https://docs.github.com/en/apps/maintaining-github-apps/transferring-ownership-of-a-github-app>
- <https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks>
- <https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps>
- <https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#resource-not-accessible>
- <https://docs.github.com/en/rest/guides/using-the-rest-api-to-interact-with-your-git-database>
- <https://docs.github.com/en/webhooks/webhook-events-and-payloads>
- <https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/redelivering-webhooks>
- <https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#list-pull-requests>
- <https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#get-a-pull-request>
- <https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api>
- <https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>

CV21 uses the list endpoint only for bounded candidate discovery in
operator-configured repositories. An exact get precedes registration and common
observation admission. Pagination and rate-limit documentation constrain DS4
transport and DS10 pass custody; they do not establish an atomic repository
snapshot, webhook completeness or lifecycle authority.

## Workflow-theory and functional-programming literature (ES-003)

- Named literature behind the ES-003 authoring-model experiments —
  structured programming (Böhm–Jacopini, Dijkstra), workflow nets and
  soundness (van der Aalst; Kiepuszewski/ter Hofstede/Bussler),
  structured concurrency (N. J. Smith), composition theory (Hughes,
  McBride & Paterson, Mokhov et al.), effects as values (Plotkin &
  Pretnar; Kiselyov & Ishii), linear logic and Petri nets (Girard;
  Engberg & Winskel; Martí-Oliet & Meseguer), idempotency doctrine
  (Helland; Garcia-Molina & Salem), and process-model metrics (Cardoso;
  Mendling) — is catalogued with per-experiment relevance in the
  [ES-003 theory reference ledger](../project/exploration/es3-workflow-ast-authoring-model/theory-references.md).
  Entries are uninspected leads for future digging, not accepted
  dependencies.
- Composable Functions (seasonedcc, TypeScript, v5.0.0) deep-inspected
  2026-08-12 as an external comparison for the ES-003 block algebra —
  not a dependency. Findings and candidate experiments in the
  [ES-003 analysis note](../project/exploration/es3-workflow-ast-authoring-model/composable-functions.md).

## Runtime libraries and deployment contracts

- GitHubKit 0.16.0 App authentication, installation scoping, cache, request,
  GraphQL, and webhook APIs, pinned in `pyproject.toml` and exercised against its
  real client with a mock HTTP transport.
- Amp Plugin API `createWebhook` durable delivery contract and
  `.amp/services.yaml` supervised-service contract, inspected from the installed
  Amp version on 2026-08-01.
