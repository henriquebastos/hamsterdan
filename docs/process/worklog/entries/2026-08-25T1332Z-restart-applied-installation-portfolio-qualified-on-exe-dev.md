# Restart-applied installation portfolio qualified on exe.dev

Clean commit `7df442608a99d50f4a5bf3955113e5a68337f6aa` produced image
`sha256:f7cb8481a4e9286be38e02af5780fe4ecb8840bf2791b8f43b0f53932da09c82`.
The archive and exact image qualified on `hamsterdan-prod`; the repeated remote
qualification reported 17 tasks OK with `changed=0`. Runtime provisioning
validated the real App, one installation account, and one admitted
`HBNetwork/demo-pr-readiness` repository from that exact image. Its repeated
run reported 39 tasks OK with `changed=0`.

The configuration-only operation then exercised both publication outcomes
without rebuilding or transferring the image. An authority-equivalent snapshot
with a comment published as one change, restoring the tracked
`deployment/config/installations.toml` published as one change, and the final
unchanged repeat reported 23 tasks OK with `changed=0`. Every run validated the
complete proposed snapshot with isolated state before publication. Because the
service was already inactive, each restart task was skipped.

Real execution also exposed Ansible's implicit Python interpreter discovery in
the configuration-only playbook. A failing-first deployment test now requires
the same explicit `/usr/bin/python3` interpreter used by runtime provisioning;
the corrected real operation emitted no discovery warning.

The systemd service remains disabled and inactive, and no exact-name container
exists. Qualification did not launch Hamsterdan, invoke an agent, write to
GitHub, change infrastructure, rotate secrets, or change App visibility. The
next effectful boundary is a separately approved supervised launch and one
bounded monitoring proof.
