# Subnet

One of the nine independent sections of the PR workflow: lifecycle, CI, escalation, review, push, conversation, summary comment, reminders, and readiness. Each subnet keeps its own notebook and inbox slots; subnets never call each other, they only leave messages. All nine run concurrently for one pull request.

Avoid: loop, concern loop, actor loop, stage (for subnets), mutation (for the push subnet), branch writes

Related: [PR Workflow](pr-workflow.md), [Notebook](notebook.md), [Chip](chip.md)
