# PR Workflow

The Petri net defining everything the app does for one pull request, from first webhook to close. One workflow instance runs per PR identity.

- Use when: the net itself, its wiring, or one PR's running instance of it.
- Do not use for: the server process around it; the workflow decides, the server executes.
- Avoid: V5 and topology as names; `v5` survives only as the on-disk version label of saved state.
- Related: [PR Identity](pr-identity.md), [Subnet](subnet.md), [Activity](activity.md)
