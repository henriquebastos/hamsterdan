# Inactive exe.dev runtime custody validated

The exact candidate from commit
`b97c7a9dcb34bf4bd5de78cdf248499ffd335f16` now has private runtime custody on
`hamsterdan-prod`. The App registration, HBNetwork installation, and configured
`HBNetwork/demo-pr-readiness` repository validated from inside the exact image.
The validation minted only short-lived installation authority and reconciled
VM-local routing state; it did not invoke an agent or perform a repository
write.

The VM stores the environment as root-owned mode `0600`, the three runtime
secret files as UID/GID 10001 mode `0600`, and durable state as UID/GID 10001
mode `0700`. The installed systemd unit is pinned to image ID
`sha256:2cf57946297b8f6f62d638163264243d3391e03fa2c4cd5c915439ce23b4447b`,
uses a read-only unprivileged container, drops all capabilities, and publishes
only to loopback when started. It remains disabled and inactive; no Hamsterdan
container or port 8000 listener exists.

Repeated provisioning validated the same App authority and reported 26 tasks
OK with `changed=0`, no failure, and no unreachable host. Independent
`systemd-analyze verify` and `systemctl show` inspection confirmed the exact
start/stop command, image identity, inactive state, and disabled state. The full
project gate passed 1,138 Python tests, nine relay tests, 44 media tests,
formatting, Ruff, typing, source distribution, and wheel.

Review established the next pre-launch design movement: one operator-controlled
App registration will admit a restart-applied configuration portfolio of
multiple GitHub installation accounts and repositories. The current executable
host and provisioning command still support one account and refuse changed
runtime inputs; the linked decision records the accepted replacement contract,
not implemented behavior.
