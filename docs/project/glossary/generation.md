# Generation

A counter of fresh starts of work on one pull request. It bumps when a new head commit lands and when a draft PR returns to ready; it does not bump on base-branch or settings refreshes. Anything computed under an older generation is discarded.

- Use when: scoping work or facts to one fresh start of the PR.
- Do not use for: review rounds or history sequence numbers; those count other things.
- Avoid: incarnation, epoch, commit generation.
- Example: a draft PR going ready starts a new generation even though no commit changed.
- Current boundary: CV21.DS2 supports only generation 1; DS9 owns successor-generation policy and implementation.
- Related: [PR Identity](pr-identity.md), [Notebook](notebook.md)
