# Watchlist

The operator-configured list of repositories Hamsterdan watches. Events from repositories not on the watchlist are ignored, and the app never writes to them.

- Use when: which repositories the app observes and may act on.
- Do not use for: event de-duplication (that is intake) or author scoping (that is a watched author).
- Avoid: admission, when speaking of repositories; admitted repository, allowlist.
- Related: [GitHub App Token](github-app-token.md), [Intake](intake.md), [Watched author](watched-author.md)
