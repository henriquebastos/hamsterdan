# Activity

One declared outside call with typed input and typed output, such as "post this comment" or "run the review agent". Petrus term; its Motus worker queues and executes activities and records each answer in the PR's history.

- Use when: any call that leaves the workflow to touch GitHub, an agent, or a clock.
- Do not use for: pure noting steps inside the workflow; those never do I/O.
- Avoid: gate, when speaking of outside calls.
- Related: [PR Workflow](pr-workflow.md), [Staleness Check](staleness-check.md), [Note](note.md)
