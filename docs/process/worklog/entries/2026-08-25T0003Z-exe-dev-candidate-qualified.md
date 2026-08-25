# Exact OCI candidate qualified on exe.dev without launch

The clean candidate from commit
`b97c7a9dcb34bf4bd5de78cdf248499ffd335f16` was exported as a compressed Docker
archive and qualified on the new `hamsterdan-prod` exe.dev VM. The VM is running
exeuntu with ownership tag `hamsterdan`, two CPUs, 4 GiB RAM, and 20 GiB disk.
The retained archive is root-only. Its SHA-256 matched after transfer, and the
loaded image ID matched the release manifest at
`sha256:2cf57946297b8f6f62d638163264243d3391e03fa2c4cd5c915439ce23b4447b`.

The remote playbook passed the host CLI, Hamsterdan `0.1.0` package, Node, Pi,
and writable durable-state checks. The first complete run changed only archive
transfer and image load. After root-only archive hardening, a final repeated
run reported 17 tasks OK, `changed=0`, no failure, and no unreachable host.
Candidate qualification did not install a systemd unit, open an application
port, transfer a GitHub credential, or start the Hamsterdan host.

The deployment path now fences VM reuse by exact name, `hamsterdan` tag,
resources, reported image, and SSH endpoint. Creation requires the exact VM
name as confirmation and has no delete operation. SSH uses a temporary
mode-0600 private key, strict known-hosts, and exe.dev's published gateway
fingerprint; a real `Linux x86_64` shell preflight rejects keys routed to the
control REPL. API and SSH credentials remain environment-only and never enter
Ansible variables or the candidate image.

Verification passed 25 deployment tests, Ansible syntax checking, the quick
static gate, and the complete project gate: 1,132 Python tests, nine relay
tests, 44 media tests, formatting, Ruff, typing, source distribution, and wheel.
The VM remains running for the next production slice. exe.dev's inability to
pin the default exeuntu base image is recorded as accepted debt before any VM
recreation; it does not change the exact OCI candidate proof.
