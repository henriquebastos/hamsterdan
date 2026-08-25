---
status: Accepted
raised: 2026-08-25
revisit: At the start of the next dedicated quality session, before tightening audit findings into quick, full, release, CI, or commit gates
related:
  - ../../workbench/rs-029-broaden-non-blocking-quality-evidence.md
  - ../../workbench/rs-030-review-maintained-complexity-baseline.md
  - ../../workbench/rs-031-review-reflective-v5-loop-assembly.md
  - ../../workbench/rs-032-strengthen-v5-rerun-reason-evidence.md
---

# Non-blocking quality audit baseline remains unresolved

RS-029 deliberately introduced broad quality evidence without turning an
unreviewed baseline into a commit gate. The accepted audit currently reports:

- 38 Ruff diagnostics, split between 37 historical Exploration findings and one
  vendored Ariad adoption-script finding;
- 72 repository-wide format findings across historical experiments,
  documentation code blocks, closed Workbench examples, and vendored material;
- 47 cyclomatic-complexity findings at threshold 10, split between 39 production
  and 8 test functions;
- two reflective-access findings in V5 topology assembly; and
- three surviving mutants in `hamsterdan.host.v5.rerun._reason`.

These findings do not block quick, full, release, CI, commits, or private
production qualification. They are still accepted obligations. A later session
must not erase them through broad auto-fixes, blanket suppressions, threshold
inflation, or deletion of evidence without first classifying ownership and
intent.

The next quality session should retrieve the detailed routes progressively:

1. use RS-030 to classify complexity findings, starting with production functions
   above 15;
2. use RS-031 to choose explicit V5 loop exports or one narrow reflection-audit
   exception;
3. use RS-032 to classify each rerun reason mutant and add only
   contract-relevant assertions; and
4. use the public-release audit debt to classify historical, documentation, and
   vendored lint and format paths before changing them.

This debt is resolved when every baseline finding has a terminal disposition:
fixed, accepted through a narrow documented exception, reclassified as frozen or
vendored evidence, or removed through an accepted owner decision. Any remaining
count must stay executable through `scripts/check audit` or `scripts/check
mutation` and recorded in the owning item.
