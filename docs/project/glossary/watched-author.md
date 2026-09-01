# Watched author

A GitHub login whose pull requests Hamsterdan monitors within a
watchlisted repository. When the operator configures no watched
authors, every author is watched.

- Use when: which PR authors the app starts journeys for.
- Do not use for: repository scope; that is the watchlist.
- Avoid: author allowlist, allowed author.
- Example: an unwatched author's PR still joins monitoring when a
  collaborator mentions the app on it; the opt-in is per PR, not per
  author.
- Related: [Watchlist](watchlist.md)
