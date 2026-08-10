# References

## Ariad provenance

- Vendored `using-ariad` package from <https://github.com/henriquebastos/ariad>
  at Git revision `7521d53983039bd808051d34bdcc56faec3277da`: package version
  `0.2.1`, method digest
  `9257e4a6b9542dc5536af2bd17e7d60a9784711faaaa926591278f4be7f8371f`,
  package digest
  `82abd3545b6d456649bc33fddb19671939ab512dd0249050a25fe7600df25572`,
  copied complete from `skills/using-ariad` to
  `.agents/skills/using-ariad` on 2026-08-09.

## Petrus provenance

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

## Runtime libraries and deployment contracts

- GitHubKit 0.16.0 App authentication, installation scoping, cache, request,
  GraphQL, and webhook APIs, pinned in `pyproject.toml` and exercised against its
  real client with a mock HTTP transport.
- Amp Plugin API `createWebhook` durable delivery contract and
  `.amp/services.yaml` supervised-service contract, inspected from the installed
  Amp version on 2026-08-01.
