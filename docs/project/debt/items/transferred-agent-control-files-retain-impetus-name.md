---
status: Accepted
raised: 2026-08-01
related:
  - CV1.DS1
---

# Transferred agent control files retain an internal Impetus name

The credential-free agent protocol still uses `.impetus/request.json` and
`.impetus/result.json` inside its disposable territory. This is not visible
GitHub grammar, identity, package coupling, or a credential boundary, so renaming
it during the App cutover would add migration noise without improving the demo.

Revisit before the first public Hamsterdan release or when the agent protocol
next changes. Rename atomically under protocol and environment-scrubbing tests;
do not add compatibility aliases unless an external consumer actually exists.
