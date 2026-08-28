# CV20 concept analysis

This working area preserves how final-system concepts are extracted from CV20.
It is reproducible intermediate analysis, not an implementation contract or an
accepted glossary. The canonical CV20 documents continue to govern Delivery.

## Objective

Identify the enduring concepts established across CV20, trace each concept
through later Delivery Stories, and review the resulting language with the
Navigator one question at a time. A concept is not accepted merely because it
appears in the candidate register.

The analysis describes canonical Hamsterdan after DS13. It does not derive
language from the implementation being replaced. `hamsterdan2`, V5, replacement
selection, migration and compatibility are not final-system concepts.

## Source authority

Read sources in this order:

1. [`../architecture.md`](../architecture.md) for fixed boundaries, ownership
   and CV20 vocabulary;
2. [`../api-contracts.md`](../api-contracts.md) for fixed names, fixed behavior
   and explicit DS-review questions;
3. [`../delivery-sequence.md`](../delivery-sequence.md) for first-use order and
   cumulative behavior;
4. [`../replacement-ledger.md`](../replacement-ledger.md) for construction and
   deletion disposition;
5. the owning DS record for its vertical behavior and acceptance; and
6. later DS records that refine or complete the candidate.

Historical exploration is provenance only. Current V5 source and tests are not
concept sources because DS13 removes that implementation rather than evolving
it.

## Reproduction method

For each DS in order:

1. Extract nouns and named relationships from Outcome, Vertical path, Fixed
   design, acceptance and Done condition.
2. Cross-check each candidate against the API contract's first-use owner,
   fixed-name status and DS-review register.
3. Trace the candidate through every later DS and DS13. Record whether the
   meaning survives, is deepened, belongs to a later owner, or disappears with
   construction.
4. Classify the item as an enduring concept candidate, subordinate vocabulary,
   an API/mechanical name, construction-only language, or an unresolved
   DS-review name.
5. Record exact source headings and line ranges in the DS worksheet and add the
   surviving candidate to the concept register.
6. Ask the Navigator one concept question. After acceptance, write one canonical
   term under `docs/project/glossary/` and link its evidence back here.

Line ranges capture the reviewed revision and may drift after edits. The named
source heading remains the stable reproduction anchor.

## Candidate states

- **Extracted:** observed in canonical CV20 but not yet traced through DS13.
- **Traced:** checked against later CV20 and believed to survive cutover.
- **Accepted:** the Navigator accepted the term and definition; a glossary link
  is recorded.
- **Excluded:** construction-only, subordinate vocabulary, or not a standalone
  concept; the reason remains recorded.
- **Deferred:** meaning or name belongs to a later DS review and cannot yet be
  settled from canonical sources.

## Progress

| Story | Extraction | Later-story trace | Navigator review | Worksheet |
|---|---|---|---|---|
| DS1 | complete | complete | pending | [DS1](ds1.md) |
| DS2 | complete | complete | pending | [DS2](ds2.md) |
| DS3 | complete | complete | pending | [DS3](ds3.md) |
| DS4 | complete | complete | pending | [DS4](ds4.md) |
| DS5 | complete | complete | pending | [DS5](ds5.md) |
| DS6 | complete | complete | pending | [DS6](ds6.md) |
| DS7 | complete | complete | pending | [DS7](ds7.md) |
| DS8 | complete | complete | pending | [DS8](ds8.md) |
| DS9 | complete | complete | pending | [DS9](ds9.md) |
| DS10 | complete | complete | pending | [DS10](ds10.md) |
| DS11 | complete | complete | pending | [DS11](ds11.md) |
| DS12 | complete | complete | pending | [DS12](ds12.md) |
| DS13 | complete | final filter | pending | [DS13](ds13.md) |

The cumulative [candidate register](candidate-register.md) is the restart point
for the cross-story analysis and later Navigator review.

## Accepted analysis policy

The Navigator ruled that the inventory models the finished Hamsterdan. A term
introduced during DS1–DS12 qualifies only if its meaning remains after DS13.
Temporary source names, the implementation being removed and replacement-only
delivery machinery do not qualify.

The first full extraction and later-story trace are complete. The Navigator
stopped the grilling before accepting a concept and paused this analysis for a
later session. Resume at DS1 with the `PR subject` candidate, then proceed one
concept question at a time. The register retains unresolved concept-versus-API
and parent-versus-subordinate classifications until the relevant question is
accepted.

No concept term or definition has yet been accepted.
