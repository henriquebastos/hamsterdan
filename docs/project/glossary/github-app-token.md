# GitHub App Token

The credential minted from the GitHub App's private key that lets Hamsterdan read and write the repositories it watches. It never leaves the server process; coding agents work on credential-free checkouts.

- Use when: the runtime credential for GitHub reads and writes.
- Do not use for: the temporary read-only token that installs the unpublished Petrus dependency; that one disappears when Petrus publishes and gets no domain word.
- Avoid: authority, when speaking of credentials; repository authority, installation authority, app credentials.
- Related: [Watchlist](watchlist.md)
