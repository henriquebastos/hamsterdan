# DS4 concept extraction

## Source

- Delivery Story: [`../cv20-ds4-settle-github-activity.md`](../cv20-ds4-settle-github-activity.md)
- Cross-boundary contracts: [`../api-contracts.md`](../api-contracts.md),
  "Bounded transport and gateway", "Lookup-first provider effect" and
  "Operation-specific authority"
- Cumulative sequence: [`../delivery-sequence.md`](../delivery-sequence.md),
  "DS4 — One lookup-first GitHub effect"

Reviewed source revision: 2026-08-28 working tree.

## Extracted behavior

DS4 settles one workflow Activity through a readiness adapter and a bounded
provider effect. A complete lookup for the stable operation precedes at most one
mutation attempt. Ambiguous or accepted-but-hidden outcomes become later
lookup-first recovery rather than an immediate retry. Readiness strictly admits
the typed terminal to the original occurrence; credentials remain with host and
provider owners.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| Outcome, lines 18–24 | Complete lookup precedes one publication attempt; hidden acceptance recovers later; exact terminal closes original occurrence | lookup-first effect, provider effect, terminal admission |
| Vertical path, lines 26–37 | Claim, provider lookup/fence, mutation, provider observation, terminal record and workflow fold are separate steps | effect attempt, provider observation, Activity settlement |
| Fixed design, lines 65–91 | Provider/readiness/workflow retain separate ownership; reads are bounded; effect cuts are distinct; credentials stay confined | provider gateway, read acquisition, credential custody, effect positions |
| Acceptance, lines 113–127 | Restart begins with lookup and performs no second mutation after hidden acceptance | lookup-first recovery and at-most-one attempt |
| API contracts / Bounded transport and gateway, lines 589–611 | Gateway owns bounded normalized reads and raw operations, not readiness classification | bounded provider gateway; list page is later discovery mechanics |
| API contracts / Lookup-first provider effect, lines 613–644 | Lookup, collision check, current-authority fence and one mutation define the reusable order | lookup-first provider effect, identity collision, ambiguous effect observation |
| API contracts / Operation-specific authority, lines 646–655 | Safeguards differ by operation rather than becoming one generic fence | operation-specific authority is a later-refined concept |
| Delivery sequence / DS4, lines 176–184 | DS4 establishes accepted-hidden recovery, physical one-effect evidence and provider correspondence | lookup-first semantics survive later effect families |

## Later ownership and refinements

- DS6 applies the established lookup-first mechanics to bounded Git object/ref
  publication and exact expected-head CAS (DS6 Fixed design, lines 78–84).
- DS7 applies the same order and one-attempt rule to CI reruns (DS7 Fixed design,
  lines 67–68).
- DS9 completes the operation-specific authority matrix: strong findings,
  mutation and rerun fences coexist with weaker reply, reminder and dashboard
  safeguards (DS9 Fixed design, lines 79–93).
- DS10 consumes DS4's bounded open-PR list-page mechanic but owns discovery-pass
  custody and exact-read-before-registration (DS10 Component Technical Stories,
  lines 49–50; Fixed design, lines 77–85).

## Subordinate vocabulary to evaluate

- accepted, refused, ambiguous and collision are outcomes within an effect
  observation, not automatically standalone concepts.
- `DashboardPublished`, `DashboardPublicationRefused` and
  `DashboardPublicationUncertain` are closed workflow API values ruled by DS3;
  DS4 supplies their provider-facing correspondence and reason vocabulary.
- claim/effect-observed/terminal-recorded and named cuts are durable positions
  or mechanics within Activity settlement.
- marker syntax, exact-read/list-page method names, pagination/rate metadata and
  physical metrics are provider API/evidence vocabulary.
- at-most-one attempt is an invariant of lookup-first execution, not a separate
  noun.

## Unresolved DS-review items

- transport, gateway, exact-read and list-page APIs and bounded metadata;
- provider effect result values, marker extraction and error taxonomy;
- attempt-claim, effect-observation and terminal-record signatures;
- readiness adapter, initial dashboard safeguard and terminal admission APIs;
- collision, stale-authority, malformed-response and correlation errors; and
- calibrated call, page, body, retained-byte, time and attempt limits.

## Construction-only exclusions

- Live/mock correspondence fixtures and separate approval posture are evidence
  and delivery controls, not domain concepts.
- Temporary provider state rollback and replacement paths do not survive DS13.

## Trace handoff

The DS5–DS13 trace is complete in the
[candidate register](candidate-register.md). It keeps DS10 discovery custody
separate from DS4's reusable list-page transport mechanic.
