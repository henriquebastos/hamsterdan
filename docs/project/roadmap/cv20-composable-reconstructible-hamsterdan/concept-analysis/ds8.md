# DS8 concept extraction

## Source

- Delivery Story: [`../cv20-ds8-recover-timers-deferred-work.md`](../cv20-ds8-recover-timers-deferred-work.md)
- Fixed timer contracts: [`../api-contracts.md`](../api-contracts.md), "Timer
  values", "Timer custody capability" and "Readiness cuts"
- Ownership and recovery contract: [`../architecture.md`](../architecture.md),
  "Fixed architecture decisions" and "Durable authority and recovery"

Reviewed source revision: 2026-08-28 working tree.

## Extracted behavior

DS8 turns workflow time intent into reconstructible deferred work. Workflow
declares an integer-microsecond timer command. Readiness durably applies it,
returns its acknowledgement through History, claims one mature timer and returns
the due fact through History. Host records only the next deadline and wakes the
subject; that wake is a hint, not timer authority. The resulting reminder,
deferred review or deferred announcement reuses an established effect seam.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| Outcome, lines 18–24 | Timer commands, mature facts, deferred effects and restart reconstruction form one path without a process-local timer | timer, deferred work, deadline |
| Vertical path, lines 26–38 | Command, acknowledgement, deadline, maturity and due-fact delivery are separate stages | timer command, timer acknowledgement, timer maturity |
| Fixed design, lines 65–82 | Workflow owns timer meaning, readiness owns durable custody, host owns wall time, and wake/posture values are hints | timer custody, wake hint, logical time |
| Tracer acceptance, lines 99–111 | One acknowledgement and maturity return through History before the established effect seam runs | timer protocol survives as production behavior; crash and correspondence are evidence |
| API contracts / Timer values, lines 320–328 | `TimerCommand`, `TimerCommandApplied` and `TimerDue` have fixed roles and integer-microsecond time | preserve timer as the concept; evaluate the three values as subordinate protocol vocabulary |
| API contracts / Timer custody capability, lines 418–438 | Apply/read/mark/claim operations remain distinct and ordered | timer custody is enduring; concrete method names are not concepts |
| API contracts / Readiness cuts, lines 520–552 | Six timer cuts and one deferred-wake cut bound progress | cut names describe mechanical boundaries, not standalone domain concepts |
| Architecture / Fixed architecture decisions, lines 64–73 | Timer command, acknowledgement, maturity, History acceptance and delivered marks remain distinct | reconstructible timer custody is final-system architecture |

## Earlier concepts completed or refined

- **Work posture:** DS8 adds `next_deadline`, but confirms posture remains a
  reconstructible host hint rather than canonical timer state.
- **Cut:** DS8 adds command, acknowledgement, maturity and deferred-wake cuts;
  it does not create a separate concept for each named cut.
- **Operation and occurrence:** deferred effects preserve the established
  Activity, operation and occurrence correlation rather than defining new
  identities.
- **Reconstruction:** retained timer custody, not a callback or wake record,
  reconstructs the next due work.

## Subordinate vocabulary to evaluate

- `TimerCommand`, `TimerCommandApplied` and `TimerDue` may be protocol members
  within **timer**, not three standalone concepts.
- Acknowledgement, maturity, due instant and deterministic ordering are likely
  parts of the timer-custody definition.
- Reminder, deferred review and deferred announcement are workflow uses of the
  timer protocol, not necessarily independent concepts introduced by DS8.
- `next_deadline`, deadline wake and wake hint belong under posture/runnable
  scheduling because they never authorize timer delivery.
- Integer microseconds are a representation invariant, not a domain concept.

## Unresolved DS-review items

- timer value fields and stable identity representation;
- timer-custody transaction and method names;
- host clock, deadline, wake and posture interfaces;
- reminder/deferred request and terminal operation grammars;
- duplicate, collision, late, stale, overflow and storage failures;
- exact names for command, acknowledgement, maturity, wake and Activity cuts;
  and
- calibrated timer, wake, History, logical-time and artifact limits.

## DS13 final-language exclusions

- Construction paths under `hamsterdan2` and `tests2` do not survive.
- Timer migration, compatibility with old timer schemas and current V5 timer
  names are expressly absent from the final system.
- Crash injection, Timeline advancement, SQLite interruption and qualification
  fixtures prove timer behavior but are not timer-domain vocabulary.
- Temporary cut names and concrete API names remain mechanical unless their DS
  review promotes them into the canonical contract.
