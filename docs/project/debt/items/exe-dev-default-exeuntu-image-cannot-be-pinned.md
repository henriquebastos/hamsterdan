---
status: Accepted
raised: 2026-08-25
revisit: Before recreating the production VM or claiming reproducible VM operating-system bootstrap
related:
  - CV19
  - ../../../../deployment/README.md
---

# exe.dev default exeuntu image cannot be pinned

CV19's first VM qualification found that exe.dev reports a default exeuntu VM
as image `boldsoftware/exeuntu`, but `new --image=boldsoftware/exeuntu` fails
because that name is not available as a public Docker image. Omitting `--image`
creates the documented default exeuntu VM, which then reports that same image
name. The current provider interface therefore exposes a stable label but not
an immutable image digest for this base.

This does not weaken Hamsterdan candidate identity. Deployment transfers the
already verified clean OCI candidate, verifies its archive checksum after
transfer, and requires the loaded Docker image ID to match the release manifest.
The Ansible playbook also refuses a target that is not Linux x86-64 or lacks
Docker. The accepted `hamsterdan-prod` VM has the exact declared name, ownership
tag, CPU, memory, disk, and reported image shape.

The remaining risk appears when the VM is recreated: exe.dev may change the
contents of default exeuntu while retaining the reported image name. Revisit
before recreation or before describing VM bootstrap as reproducible. Resolution
requires either an exe.dev-supported immutable default-image reference or a
Hamsterdan-owned, pinned, qualified base image. Do not expand the current
no-effects candidate qualification into custom-image maintenance.
