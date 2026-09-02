# Subnet

One of the nine independent sections of the PR workflow: lifecycle, CI, escalation, review, push, conversation, summary comment, reminders, and readiness. Each subnet keeps its own notebook and inbox slots; subnets never call each other, they only leave messages. All nine run concurrently for one pull request.

- Use when: one of the nine sections of today's PR workflow.
- Do not use for: the reusable packaged form with declared pins; that is a chip.
- Avoid: loop, concern loop, actor loop; stage, when speaking of subnets; mutation and branch writes, for the push subnet.
- Related: [PR Workflow](pr-workflow.md), [Notebook](notebook.md), [Chip](chip.md)
