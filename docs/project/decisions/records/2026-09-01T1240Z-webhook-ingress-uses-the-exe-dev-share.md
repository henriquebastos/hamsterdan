---
status: Decided
raised: 2026-08-31
decided: 2026-09-01
recorded: 2026-09-01T1240Z
deciders:
  - Henrique (Navigator)
related:
  - CV19
  - ../../roadmap/cv19-private-v0-1-production/launch-runbook.md
  - 2026-08-31T2056Z-the-alpha-is-the-cv19-v1-launch.md
---

# Webhook ingress uses the exe.dev share

## Decision

Production webhook ingress for the CV19 launch is the exe.dev HTTPS share:
`https://hamsterdan.example.invalid/` proxies to port 8000 on the VM, set to
public so GitHub can deliver. The GitHub App webhook URL now points at
`https://hamsterdan.example.invalid/github/webhooks` (updated 2026-09-01,
verified via the App API: content type json, secret set, TLS verification
on). The Amp relay used during qualification is no longer the production
path. The service keeps its qualified `127.0.0.1:8000` bind unchanged.

## Rationale

The open runbook gap assumed the share would require a non-loopback bind and
re-qualification. An empirical probe disproved that: with a temporary
listener on the VM's `127.0.0.1:8000`, an external HTTPS POST to the share
URL reached the loopback listener end to end with a 202, and the
webhook-critical headers (`X-Hub-Signature-256`, `X-GitHub-Event`,
`Content-Type`) plus the JSON body arrived intact through the proxy. That
makes the share the smallest change that closes the gap: no bind change, no
new credential, no extra daemon, TLS terminated at the exe.dev edge, and
private-by-default semantics until explicitly set public.

Trade-offs accepted: there is no durable delivery queue upstream — while the
service is down, deliveries fail at the edge and GitHub's **Recent
deliveries → Redeliver** is the recovery path, which is already the
runbook's rollback stance. The hostname is coupled to the VM name; a
provider-independent tunnel remains the recorded alternative if the VM ever
moves or is renamed.

## Consequences

- The runbook's "open gap" is resolved; Phase 1's ping-redelivery proof runs
  against the share URL once the Navigator approves the launch.
- While the service stays inactive, GitHub records failed deliveries against
  the new URL; they are redeliverable and expected.
- Rollback of the ingress itself is one command (`share set-private`) or
  repointing the App webhook URL; neither touches the VM.
