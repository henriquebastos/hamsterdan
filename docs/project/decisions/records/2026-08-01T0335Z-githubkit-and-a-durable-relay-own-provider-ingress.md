---
status: Decided
raised: 2026-08-01
decided: 2026-08-01
deciders:
  - Henrique (Navigator)
related:
  - CV1.DS1
---

# GitHubKit and a durable relay own provider ingress

## Decision

Hamsterdan uses GitHubKit 0.16.0's App authentication strategy for App JWTs,
installation-token minting, in-process caching, expiry, and reminting. Hamsterdan
does not persist or expose raw installation tokens. It owns registration and
installation validation, selected-repository routing, per-repository client
scoping, request metadata, effect authority, and restart behavior.

Every provider request opens a GitHubKit sync client in the executing context
and consumes any streamed response before that scope closes. GitHubKit's
entered client is context-local and is not retained across host worker
contexts. Startup validates both the App registration permissions and the
permissions accepted by the selected installation; a registration update that
still awaits installation-owner approval fails closed.

The canonical HBNetwork deployment uses an App-owned webhook. In an Amp orb, a
project plugin registers a durable Amp webhook capability and forwards only the
exact body plus four allowlisted GitHub headers to the loopback host. The relay
does not know the webhook secret and returns only after the host proves durable
custody. The capability URL is a host secret stored mode `0600`; it is not a
browser portal, product API, or workflow authority.

The host verifies signatures before parsing, stores a sanitized observation
rather than the raw payload, deduplicates by GitHub delivery UUID, retries with
bounded exponential backoff, parks exhausted deliveries, and periodically
reconciles durable PR Instances. One process supports one App registration and
one installation account, with one exact repository in each operation token.

## Rationale

GitHubKit removes custom JWT/token refresh machinery while preserving the
project's host-only secret boundary. A normal Amp portal requires viewer
authentication and cannot receive GitHub deliveries; the durable relay provides
the provider-facing queue and orb wake-up without weakening host signature
verification or coupling the App to Amp's agent surface.

## Consequences

- Installation credentials remain short-lived provider artifacts; only App key
  and webhook secret require durable host custody.
- The HBNetwork comment/effect route requires Pull requests write in addition
  to Issues write. GitHub denied live PR-thread comments with Pull requests read
  and advertised the write grant in its accepted-permissions response. Host
  code still exposes no merge, formal-review, or PR-edit operation.
- Deployment outside Amp may replace the relay with any HTTPS ingress that
  preserves exact bytes/headers and the same durable-custody contract.
- GitHub does not automatically redeliver failed webhook deliveries. Periodic
  sweep repairs already-known PR Instances; a delivery missed before first
  admission must be redelivered from GitHub's delivery UI.
- The first instance is a private HBNetwork-owned App. GitHub permits changing
  an App's visibility later; generalized public installation and multi-account
  tenancy remain out of scope.
