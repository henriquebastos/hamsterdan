# DS2 concept extraction

## Source

- Delivery Story: [`../cv20-ds2-admit-fold-pr-observation.md`](../cv20-ds2-admit-fold-pr-observation.md)
- Decided observation model:
  [`../../../decisions/records/2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md`](../../../decisions/records/2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md)
- Cross-boundary contracts: [`../api-contracts.md`](../api-contracts.md),
  "Provider acquisition and observation identity", "Source-neutral ingress
  admission", "Shared step result" and "Delivery receipt and custody"

Reviewed source revision: 2026-08-28 working tree.

## Extracted behavior

DS2 separates provider acquisition, workflow observation and workflow admission.
A verified webhook becomes an immutable provider snapshot plus source-specific
provenance. Readiness projects focused observations, stages one immutable
manifest and manifest-scoped grant, classifies each entry against Petrus
History, and folds a novel `HeadSeen`. Host acknowledges the delivery only after
readiness reports accepted or already-accepted posture for that exact delivery.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| Outcome, lines 21–28 | Snapshot/provenance, manifest/grant, History classification, fold and acknowledgement are distinct owners and steps | acquisition, snapshot, provenance, ingress, delivery custody |
| Vertical path, lines 33–41 | The same value crosses provider, host, readiness and workflow boundaries | source-neutral admission and exact delivery acknowledgement |
| Fixed design, lines 80–95 | Snapshot, provenance, branch tips, route identity, HeadSeen and local incarnation have separate meanings | pull request snapshot, observation provenance, branch tip, acquisition identity, head seen, local incarnation |
| Fixed design, lines 96–120 | Canonical bytes, ObservationKey, HistoryAdmissionId, manifest/grant/entry and closed decisions define semantic admission | observation key, History admission identity, ingress manifest, ingress entry, admission grant, admission decision, observation admission |
| Fixed design, lines 100–104 | Duplicate, corroborating and collision cases differ by acquisition identity, key and canonical bytes | corroboration, acquisition collision, semantic collision |
| Fixed design, lines 126–140 | Receipt, inbox retention, terminal acknowledgement and tombstone compaction are distinct custody facts | inbox receipt, delivery acknowledgement, delivery posture, delivery tombstone |
| API contracts / Provider acquisition and observation identity, lines 160–208 | Fixed cross-boundary names and equality rules; read provenance and currentness belong later | preserve fixed semantics; defer DS4/DS9 extensions |
| API contracts / Source-neutral ingress admission, lines 332–387 | Exactly one manifest and grant exist per acquisition; History is the sole admission ledger | ingress concepts and no second ledger |
| API contracts / Delivery receipt and custody, lines 724–750 | Three receipt layers and guarded retained-to-acknowledged transition are fixed | distinguish transport receipt, InboxReceipt and acknowledgement |

## Later ownership already explicit

- DS4 introduces exact-read acquisition mechanics but must reuse this admission
  path.
- DS9 owns successor incarnations, `CurrentnessWitness` and lifecycle authority.
- DS10 owns unknown-PR discovery before exact read and common admission.

`ProviderReadId`, `PolicySeen` and `CurrentnessWitness` therefore require the
whole-CV20 trace before deciding whether DS2 defines them or only prepares for
their later owner.

## Subordinate vocabulary to evaluate

- The eight AdmissionDecision outcomes may belong inside one admission-decision
  definition rather than eight glossary files.
- Individual cut names may be instances of the general cut concept rather than
  standalone concepts.
- `ObservationAdmission` may be a useful concept or only the name of a
  reconstructible index; later usage must decide.
- Receipt state names and compare-and-swap mechanics may remain inside delivery
  custody rather than become independent terms.

## Unresolved DS-review items

- exact webhook, snapshot, provenance and subject shapes;
- codecs and boundary model placement;
- retain, stage, classify, admit, fold and acknowledge call names;
- durable schemas and bounded provenance representation;
- collision, corroboration, refusal and repair payloads; and
- calibrated byte, row, page, History, journal and artifact limits.

## Trace handoff

The DS3–DS13 trace, including DS9's completion of incarnation/currentness and
DS13's final-language filter, is complete in the
[candidate register](candidate-register.md). Navigator review is paused.
