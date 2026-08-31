# Generation

A counter of fresh starts of work on one pull request. It bumps when a new head commit lands and when a draft PR returns to ready; it does not bump on base-branch or settings refreshes. Anything computed under an older generation is discarded.

Avoid: incarnation, epoch, commit generation

Related: [PR Identity](pr-identity.md), [PR Workflow](pr-workflow.md)
