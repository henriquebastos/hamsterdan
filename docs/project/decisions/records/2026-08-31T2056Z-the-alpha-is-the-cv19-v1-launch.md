---
status: Decided
raised: 2026-08-31
decided: 2026-08-31
recorded: 2026-08-31T2056Z
deciders:
  - Henrique (Navigator)
related:
  - CV19
  - CV21
  - CV22
  - ../../glossary/index.md
  - ../../../product/what-hamsterdan-is.md
  - 2026-08-28T1453Z-cv20-fragments-into-outer-system-and-workflow-replacement-values.md
---

# The alpha is the CV19 v1 launch

## Decision

The first production alpha is CV19's private `v0.1.0` launch of the current v1
runtime. CV19 resumes as the delivery focus. CV21 continues as the quality
track at whatever pace protects the Navigator, and no longer gates the alpha.
CV22 is unchanged. The supervised launch itself still requires its separate
explicit Navigator approval, exactly as CV19 already states.

## Rationale

The rewrite was on the critical path only because "understanding" was
conflated with "rewritten". The 2026-08-31 domain-language reset decoupled
them: the project glossary and the plain-language identity page were extracted
from v1's actual behavior, so v1 is now explainable at the concept level
without reading its source. Meanwhile v1 carries the project's strongest
evidence (eleven scenarios, a real three-actor repair on a live PR,
crash-and-replay simulation), and CV19's remaining work is small: verify the
GitHub Actions billing blocker, one approved supervised monitoring journey,
and the tag.

## Consequences

- Roadmap: CV19 returns to Active as the focus; CV21 stays Active as the
  quality track with production pressure removed.
- Waiting for CV21 + CV22 before shipping is rejected as the alternative.
- Review trigger: this record's delivery consequence closes when `v0.1.0` is
  tagged; a launch incident that v1's opacity makes unmanageable reopens the
  priority question.
