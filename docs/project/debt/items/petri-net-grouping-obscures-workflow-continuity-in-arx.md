---
status: Accepted
raised: 2026-08-04
related:
  - CV4.DS1
  - https://github.com/henriquebastos/petrus-arx
---

# Petri net grouping obscures workflow continuity in Arx

The read-only replay of PR47's 1,583-record Petrus History exposed a design
problem that the GitHub-oriented demo did not make visible. Hamsterdan's net is
flat, and many names group transitions by structural category—such as
`execute.*`, `work.*`, and `retire.*`—while shared workflow state remains at the
root. The resulting whole-net view repeatedly connects category islands through
root nodes instead of presenting the continuity of admission, review, mutation,
recovery, readiness, and lifecycle journeys.

The replay also exposed a limitation in Arx's island-first placement. Arx uses
only the first dotted path segment as the island owner. Nested namespace paths
therefore do not produce nested visual islands even though sub-islands are a
valid and necessary representation. Every namespace boundary expressed by a
dot must be eligible to create a recursively nested island, with composition
and routing preserving the parent-child relationship.

These are related but separate follow-up obligations and should be handled in
dedicated threads:

1. **Hamsterdan net design:** revisit names, boundaries, and composition so
   grouping follows coherent workflow continuity rather than implementation or
   effect categories. Preserve the existing behavioral, authority, and
   at-least-once effect contracts; do not reshape the net merely to improve one
   recording.
2. **Arx layout semantics:** replace first-segment-only ownership with recursive
   namespace islands. Each successive dotted segment should form a nested
   sub-island where present, and ordinary root nodes should remain root only
   when the schema actually places them there.

Completion requires an agreed continuity-oriented Hamsterdan schema, an Arx
whole-net view that renders all recursive namespace levels, and replay evidence
showing the complete net and its active paths without presentation-only aliasing
or fabricated arcs. This item records the obligation only; the one-off PR47
replay conversion and video must not become a compatibility layer or product
feature in either repository.

RS-001 resolved the Hamsterdan half on 2026-08-10: independent concern tokens,
exact Activity places, relational projection, explicit publication continuity,
and invariant-named retirement now make the executable topology traceable in
workflow order. The Arx recursive-island and replay-visualization obligation
remains open; this item stays accepted for that external portion.
