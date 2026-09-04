---
status: Accepted
raised: 2026-09-04
revisit: Before the next production evidence capture
related:
  - ../../roadmap/cv19-private-v0-1-production/proof/pr80.md
  - ../../roadmap/cv19-private-v0-1-production/proof/pr83.md
---

# 1. Full-page capture dimensions do not detect repeated tiles

PR80 and PR83 each produced full-page screenshots containing repeated viewport
tiles even though PNG width and height matched the document dimensions. In
PR83, `06-reviewing.png` and `17-repair-requested.png` failed visual inspection.
Dimensions alone therefore cannot qualify browser evidence.

The accepted initial PR83 still preserves startup ordering. A replacement
capture preserves the repair instruction and App commit. A separate anonymous
browser session produced visually valid replacement and later stills while the
original session retained the recording. This is an observed workaround, not
a proven cause or permanent correction.

Before another capture, use a separate session for stills, inspect every full
PNG, retain rejected evidence with explicit status, and recapture each required
checkpoint before advancing its irreversible GitHub state. A durable capture
fix should reject repeated tiles mechanically and preserve truthful before/after
DOM evidence. No provider or runtime behavior should change to repair media.
