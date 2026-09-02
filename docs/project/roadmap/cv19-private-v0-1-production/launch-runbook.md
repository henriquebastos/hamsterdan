# CV19 launch runbook — the supervised alpha launch

Owned by the [alpha decision](../../decisions/records/2026-08-31T2056Z-the-alpha-is-the-cv19-v1-launch.md).
Nothing in this runbook starts the service by itself: Gate A is the Navigator's
explicit launch approval and Gate B the separate `v0.1.0` tag approval, exactly
as CV19's done condition requires. Terms follow the
[project glossary](../../glossary/index.md).

## Ingress — resolved 2026-09-01

**How do GitHub webhooks reach the VM?** Resolved by the
[exe.dev share decision](../../decisions/records/2026-09-01T1240Z-webhook-ingress-uses-the-exe-dev-share.md):
`https://hamsterdan.example.invalid/` proxies publicly to the VM's port 8000 and
reaches the qualified `127.0.0.1:8000` bind unchanged (proven with an
end-to-end probe carrying the webhook headers). The App webhook URL points at
`https://hamsterdan.example.invalid/github/webhooks`. Phase 1 still owes the
live proof: one ping redelivery landing in the service's webhook inbox.

## Phase 0 — pre-launch verification (no GitHub effects)

1. Billing: confirm one fresh CI run on `HBNetwork/demo-pr-readiness` starts
   and finishes. The `henriquebastos` account is billing-blocked (verified
   2026-08-31); the demo repo lives under HBNetwork and must be proven
   unaffected.
2. Candidate: `deployment/release.py verify` against the accepted manifest, and
   a repeated `deploy.py --manifest ...` reporting `changed=0`.
3. Runtime: repeated `runtime.py provision --manifest ...` and
   `runtime.py configure --file deployment/config/installations.toml` both
   reporting `changed=0`; the watchlist contains exactly
   `HBNetwork/demo-pr-readiness`.
4. App registration: permissions/events contract validates, webhook Active,
   secret set, broker workflow current (`hamsterdan-demo prepare-broker`
   reports current).
5. Ingress gap above resolved and recorded.

## Gate A — Navigator approves the supervised launch and one bounded journey

Approval covers starting the service and running exactly one monitoring
journey on the demo repository. It does not cover the tag.

## Phase 1 — start and prove ingress

1. Over the fingerprint-pinned SSH: `systemctl enable --now hamsterdan`.
2. Health from the VM loopback: `/healthz` bounded and secret-free, failed
   inbox count zero.
3. Request one GitHub ping redelivery; it must land in the webhook inbox with
   a 202 answer and show as processed, not failed.

## Phase 2 — the bounded monitoring journey

With the human operator's own credentials (never the GitHub App token):

1. `scripts/hamsterdan-demo create --scenario clean-green` on the demo repo.
2. Watch the journey end to end: intake of the opened event, the summary
   comment appearing and updating, CI going green for the current head, and
   the ready comment posted exactly once for that generation.
3. Mid-journey, one supervised service restart. After restart the workflow
   must converge with no duplicate comments and no unresolved activities;
   this is the restart-posture proof.
4. `scripts/hamsterdan-demo inspect --pr <n>` must pass every ownership,
   marker, workflow-head, and attribution check.

## Phase 3 — evidence, per CV19 done condition 3

Preserve: PR URL and number, exact heads and generation, delivery UUIDs and
inbox dispositions, Actions run IDs and conclusions, the summary and ready
comment URLs with App ownership, inspection JSON before and after the restart,
and the zero-duplicate, zero-unresolved assessment. Record it all in one
worklog entry.

## Phase 4 — close

1. Close the scenario PR unmerged.
2. Commit and push the accepted evidence.
3. Gate B — the Navigator separately authorizes the private `v0.1.0`
   release/tag; create it and record deployment recovery and rollback facts
   without credentials.

## Rollback

`systemctl stop hamsterdan`, confirm the process is down. The service down is
the safe state: deliveries queue durably upstream and GitHub's **Recent
deliveries → Redeliver** covers anything missed. Follow the operator runbook's
isolated-handoff rules if the legacy PAT service must take over; never run two
writers.

## Deployment recovery and rollback facts — recorded at v0.1.0 (Gate B, 2026-09-01)

The `v0.1.0` tag points at revision `7df442608a99d50f4a5bf3955113e5a68337f6aa`,
the accepted candidate behind image
`sha256:f7cb8481a4e9286be38e02af5780fe4ecb8840bf2791b8f43b0f53932da09c82`.

- **The artifact, not the build, is authoritative.** Image builds are not
  bit-reproducible: rebuilding the same clean revision produced a different
  image identity (`sha256:7083b925…`). Recovering the accepted artifact means
  exporting it from where it runs (`docker save | gzip` over the pinned SSH,
  `docker load` locally preserves the image id) and reconstructing the
  manifest — never trusting a rebuild to reproduce it.
- **Deploy and provision are idempotent.** Repeating `deploy.py --manifest …`
  reported ok=17 changed=0 and `runtime.py provision` ok=39 changed=0
  (configure ok=23 changed=0) against the healthy VM, so either can be re-run
  as a recovery step without side effects.
- **Restart converges.** A supervised `systemctl restart hamsterdan`
  mid-journey reconverged in ~11 s with no duplicate comments and no
  unresolved activities (proven on PR #62).
- **Missed deliveries are redeliverable.** There is no durable queue upstream
  of the exe.dev share; while the service is down GitHub records failed
  deliveries, and **Recent deliveries → Redeliver** replays them. Prefer a
  ping over redelivering a real event: a real `workflow_run` redelivery re-woke
  monitoring on an unrelated open PR during launch.
- **Ingress detaches in one credential-free step.** `share set-private` on
  exe.dev, or repointing the App webhook URL; neither touches the VM or any
  secret.
