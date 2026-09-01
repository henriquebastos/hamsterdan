# Supervised launch and clean-green journey on hamsterdan-prod

The Navigator approved Gate A on 2026-09-01 and the launch ran the same day.
Phase 0 closed first: a fresh demo-repo CI run disproved the billing blocker;
the accepted image `sha256:f7cb8481a4e9286be38e02af5780fe4ecb8840bf2791b8f43b0f53932da09c82`
was exported from the VM itself, verified locally by `release.py verify`, and
the repeats reported `deploy.py` ok=17 `changed=0` and `runtime.py provision`
ok=39 `changed=0` (configure ok=23 `changed=0`); the App contract matched the
documented permission and event set; and the
[exe.dev share decision](../../../project/decisions/records/2026-09-01T1240Z-webhook-ingress-uses-the-exe-dev-share.md)
closed the ingress gap. A rebuild of the same clean commit produced a
different image identity (`sha256:7083b925…`), confirming image builds are not
bit-reproducible; the accepted artifact on the VM stays authoritative.

Phase 1: `systemctl enable --now hamsterdan` at 2026-09-01, `/healthz`
answered 200 in 12 ms from the loopback, secret-free, with an empty inbox and
a clean scheduler. No ping delivery existed, so the most recent real
`workflow_run` delivery (GUID `6efee190-a5b4-11f1-8fe9-f9d6a805e525`) was
redelivered through `https://hamsterdan.example.invalid/github/webhooks`: GitHub
recorded OK 202 and the service processed it to a terminal disposition. Since
the cutover, zero deliveries have failed. Side effect, reported for honesty:
that real event re-woke monitoring on the still-open hero-review PR #61,
which posted one fresh readiness advisory there and converged; a future
launch should prefer a ping or a synthetic delivery.

Phase 2, the bounded journey on PR
[#62](https://github.com/HBNetwork/demo-pr-readiness/pull/62)
(`hamsterdan/clean-green-20260901-165449`, head
`3ff7d1067d8437340e39d2ad38c06ab4631a7c4f`, base `a83e9223…`):

- Intake: `pull_request.opened` GUID `dc9e7910-a625-11f1-8237-a613ce5e5b8f`
  delivered 16:54:58Z, OK 202.
- Dashboard comment
  [5497444124](https://github.com/HBNetwork/demo-pr-readiness/pull/62#issuecomment-5497444124)
  posted 16:56:37Z by `hamster-dan[bot]` and updated through the journey.
- CI: Actions run 33534657038 (`ci`) concluded success for the exact head.
- Ready comment
  [5497449960](https://github.com/HBNetwork/demo-pr-readiness/pull/62#issuecomment-5497449960)
  posted 16:57:06Z, exactly once, marker
  `ready:3ff7d1067d8437340e39d2ad38c06ab4631a7c4f:i1`.
- Supervised restart: `systemctl restart hamsterdan`, active again at
  16:57:23Z (`NRestarts=0` under systemd's counter — a commanded restart, not
  a crash). The workflow converged after the restart: the dashboard's final
  update landed 16:57:34Z with checks success, zero findings, review clear,
  and `announced` for the journey head. No duplicate comments, no unresolved
  activities; the final inbox shows every item terminal and the scheduler
  reports zero degraded instances.
- `hamsterdan-demo inspect --pr 62`: `ok=true`, all six checks pass —
  pull identity 1316665126, comment ownership `hamster-dan[bot]`, dashboard
  present, readiness advisory present, zero legacy markers, workflow head
  equal to the journey head. Inspection ran before and after the restart with
  the same passing outcome. Attribution: author and committer
  `henriquebastos`, the human operator's own credentials; the App token wrote
  only App comments.

Phase 4 closed the scenario PR unmerged. The service remains enabled and
active on the accepted image. The `v0.1.0` tag remains behind Gate B, which
the Navigator authorizes separately.
