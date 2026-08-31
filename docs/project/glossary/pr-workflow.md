# PR Workflow

The Petri net defining everything the app does for one pull request, from first webhook to close. One workflow instance runs per PR identity. `v5` survives only as the on-disk version label of saved state, never as the workflow's name.

Avoid: V5 (as a name), net_v5 (in prose), topology

Related: [PR Identity](pr-identity.md), [Activity](activity.md)
