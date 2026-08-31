# Notebook

The single record where one subnet keeps everything it remembers about this pull request, built up fact by fact, never by re-reading the PR. Exactly one copy exists: it travels inside any outside call the subnet makes, so a second call cannot start until the notebook is back. Each entry is stamped with the generation it belongs to.

- Use when: one subnet's private running record.
- Do not use for: the PR's append-only history log; the history is the source of truth, notebooks are rebuilt from it.
- Avoid: baton, memory, snap, ladder, projection; state, when speaking of this record.
- Related: [Subnet](subnet.md), [Generation](generation.md), [Note](note.md)
