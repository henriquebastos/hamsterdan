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
