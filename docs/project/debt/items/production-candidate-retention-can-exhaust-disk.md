---
status: Accepted
raised: 2026-09-04
revisit: Before the next production deployment
related:
  - ../../roadmap/cv19-private-v0-1-production/index.md
---

# 1. Production candidate retention can exhaust disk

Deploying the PR79 review-input correction filled the 20 GB production disk
after the image loaded. Seventeen retained candidate archives occupied about
2.8 GB, alongside seventeen Docker images. Ansible could not create its next
temporary directory. The running service and durable state were retained.

Removing three old unused image tags and their matching candidate directories
(`7df4426`, `b97c7a9`, `f4e443b`) recovered 2.5 GB. The current, preceding, and
new candidate images remained available. Qualification then completed with
`changed=0, failed=0`; runtime provisioning also repeated without changes.

The deployment path has no bounded candidate-retention policy or free-space
preflight. Before another deployment, check capacity and identify unused
candidate artifacts. A durable fix should reserve enough space before transfer
and remove only explicitly eligible deployment artifacts while preserving the
running image, a qualified rollback candidate, and all application state.
Do not use an unrestricted Docker or filesystem prune as that policy.

RS-036 revisited this obligation before deploying `2f1b646`: the VM had 2.5 GB
free, and the current `14f41d8` and prior `e3a79bb` candidates were retained.
The deployment completed without cleanup or capacity failure. The manual check
satisfied this promotion's prerequisite; automated preflight and bounded
retention remain unresolved before future deployments.
