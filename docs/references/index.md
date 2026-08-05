# References

## Petrus provenance

- Petrus namespace migration and accepted application dependency:
  `henriquebastos/petrus@cd1187e44926d6a80e4a3538ad79762618d32a8b`,
  inspected 2026-08-01.
- Qualified workflow source: `examples/pr_readiness_next/` and
  `tests/examples/pr_readiness_next/` at that commit.
- Petrus Agenticus adoption dependency:
  `henriquebastos/petrus@ceb36d5db5b3bc9ed13ebc02a9971708d9461b20`,
  inspected 2026-08-05. Hamsterdan consumes the exact Git revision and does not
  assume package publication.

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
- <https://docs.github.com/en/webhooks/webhook-events-and-payloads>

## Runtime libraries and deployment contracts

- GitHubKit 0.16.0 App authentication, installation scoping, cache, request,
  GraphQL, and webhook APIs, pinned in `pyproject.toml` and exercised against its
  real client with a mock HTTP transport.
- Amp Plugin API `createWebhook` durable delivery contract and
  `.amp/services.yaml` supervised-service contract, inspected from the installed
  Amp version on 2026-08-01.
