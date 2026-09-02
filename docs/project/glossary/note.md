# Note

Writing one incoming fact into a notebook: a pure function that takes the fact plus the current notebook and returns the updated notebook and any outgoing messages.

- Use when: the pure step that folds one fact into a subnet's notebook.
- Do not use for: activities; noting never does I/O.
- Avoid: fold.
- Related: [Notebook](notebook.md), [Activity](activity.md)
