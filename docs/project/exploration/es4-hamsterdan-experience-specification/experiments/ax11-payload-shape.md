# AX11 — Payload shape contracts: ports carry types, not color strings

## Question

AX5 MISSED #5, from AX4's one genuine composition finding: port
fusion checked *colors*, but the downstream handler needed *fields*.
`ProvisionalHead {provisional_head, reused}` fused into a consumer
wanting `(kind, operation, head)` because the strings matched, and
the adapter silently invented its marker from the head alone. Petrus
is no stricter — `Arc.color` is a string, "a typed arc admits its
color only (nominal match)" (`petrus/impetus/petrinet/schema.py`).
Question: what does a port contract that carries payload *shape*
look like, what should the fusion rule be, and how much of it do
pyright and ty enforce at edit time?

Spike: [ax11-payload-shape/](ax11-payload-shape/) — 15 tests, all
passing (11 runtime + 4 checker-harness); read-only imports of
production models; no production edits.

## The fusion rule: nominal identity, with shape as the diagnostic

The obvious rule — fuse whenever shapes are structurally compatible —
is wrong, and production itself is the proof:

```python
# contracts/readiness.py:546-570 — IDENTICAL field lists
class ChangeResult(WorkflowModel):
    epoch: int; head: str; ok: bool; provisional_head: str = ""
    fingerprint: str = ""; lineage: str = ""; operation: str = ""; …

class RepairResult(WorkflowModel):
    epoch: int; head: str; ok: bool; provisional_head: str = ""
    fingerprint: str = ""; lineage: str = ""; operation: str = ""; …
```

A structural rule would happily route a change result into the
repair acceptor — and corrupt repair lineage (`repair_used`,
`repair_fingerprint`, AX10's budget fence). Same shape, different
meaning. So the spike's rule set:

```python
fuse(Port("repair.settled", RepairResult), Port("accept.repair", RepairResult))  # ok
fuse(Port("change.settled", ChangeResult), Port("accept.repair", RepairResult))
# ShapeError: … same shape is not same meaning — adapt explicitly

fuse(Port("committed", ProvisionalHead), Port("announce", FindingPublicationRequest))
# ShapeError: cannot fuse port 'committed' (ProvisionalHead) into port
# 'announce' (FindingPublicationRequest): base_head: missing …; epoch:
# missing …; findings: missing …; operation: missing (producer has
# provisional_head, reused); …
```

Shape is never the *rule* — it is the *explanation*: the refusal
lists exactly the required consumer fields the producer cannot
provide (absent, or annotated incompatibly: `epoch: is str, consumer
wants int`). The AX4 mystery becomes a named, field-level error at
composition time. This is one more instance of the settled doctrine:
**types validate compatibility; named ports define topology** — now
with "type" meaning fields, not a string.

## Adapters: the signature is the contract

Crossing types requires an explicit adapter, and its contract is
*inferred* from its annotations — AX26's sharpened lesson (inference
is safer than declaration, because a single source cannot lie):

```python
before (AX4):                          after:
def draft(committed: dict) -> dict:    def announce_repair(
    head = committed["provisional_head"]        result: RepairResult,
    return {"operation": f"announce-{head}",    ) -> FindingPublicationRequest:
            "head": head}                   return FindingPublicationRequest(
transform("announce_commit", draft,             epoch=result.epoch, …)
    accepts="ProvisionalHead",          announce = adapter(announce_repair)
    returns="FindingPublicationRequest")   # accepts/returns read from the
                                            # signature; untyped fn refused
```

`fuse_through(producer, adapter, consumer)` is just two nominal
fusions, so a mis-declared adapter is refused at the exact seam,
naming both sides (tested).

## Guard fields: AX26's named limit, closed

A guard referencing a field the payload cannot have now fails at
composition time, traversing nested dataclasses:

```python
guard_fields(Port("classify", ConversationClassificationRequest),
             "comment.actor_login", "control.repair_in_flight")   # ok — nested
guard_fields(Port("repair.settled", RepairResult), "risk_score")
# ShapeError: RepairResult has no field 'risk_score' (has agent_cleanup_category,
# agent_result_category, epoch, fingerprint, head, lineage, ok, …)
guard_fields(Port("repair.settled", RepairResult), "epoch.value")
# ShapeError: epoch is int, which cannot have field 'value'
```

This answers ES-003 AX7's open question — the guard AST does need
knowledge of the data type, and the port payload is where that
knowledge lives.

## The static twins: shape errors are ty's sweet spot

AX26 found ty 0.0.63 missed 4/9 combinator mistakes — all
generic-parameter constraints. Shape errors are different: they are
STRUCTURAL (attribute access, argument type, return type), which is
exactly what ty's no-false-positives posture already enforces. The
harness runs both checkers over the fixtures and asserts line by
line:

| Mistake (static twin of…) | pyright 1.1.411 | ty 0.0.63 |
| --- | --- | --- |
| phantom field access (guard_fields refusal) | caught | **caught** |
| adapter returning the wrong type (fuse_through refusal) | caught | **caught** |
| wrong payload type passed (nominal fuse refusal) | caught | **caught** |
| good adapter over production models | clean | clean |

The project's own CI checker (`scripts/check` runs `ty check src`)
already enforces the entire adapter layer today, on unmodified
pydantic `WorkflowModel` dataclasses, with zero annotation burden
beyond ordinary signatures. The split of labor that emerges:

```text
edit time (ty, in CI today)   adapter bodies, arguments, returns — structural
compose time (deterministic)  fusion rule, shape diffs, guard paths — semantic
run time (frozen engine)      unchanged
```

## What this implies for the Petrus speculation

"Bind types instead of strings" (Navigator direction, ES-003) now has
a measured shape: the runtime's nominal string colors are *fine as
identity* — nominal is the correct fusion rule anyway — but the
authoring layer above should hold `Port(name, payload_type)` so that
shape diffs, guard validation, and checker enforcement all come from
one declaration. The engine needs no change; the color string becomes
a *derived* projection of the payload type (as ES-003 AX26 already
demonstrated with `_color(tp)`).

## Divergence classification

```text
color-string-only port contracts   MISSED in production AND prior spikes —
                                    now closed: Port(name, payload_type)
structural fusion                  REJECTED — ChangeResult/RepairResult twins
                                    prove same shape ≠ same meaning
nominal fusion + explicit adapters REQUIREMENT-GRADE RULE — kept, now enforced
guard-field validation             CLOSED (AX26 limit) — deterministic, nested
adapter contracts from signatures  ADOPTED — single source of truth
```

## Verdict

**Promising; continue.** The port contract is `Port(name,
payload_type)`: names give topology, nominal types give identity,
shape gives diagnostics, signatures give adapters, and the payload
type gives guards their field authority. The static layer is
stronger here than AX26's combinator layer — ty catches everything
today because shape errors are structural — so the adapter seam is
where edit-time checking pays off first. AX5's MISSED list now has
one unspiked item left: human observation folding (#7), plus the
finding-lineage product choice (#6).
