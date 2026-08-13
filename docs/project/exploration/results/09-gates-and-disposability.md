# 9 — Gates and disposability

**Rely on this: the only way work becomes world-visible is through a
gate — so everything before the gate is disposable, and simplicity
beats saved work.**

## What it is

Classifying a real system's entire effect surface produced exactly two
world-mutation gate types:

```text
LOOKUP-FIRST GATE   idempotent publications (comments, dashboards,
                    notes): operation identity + look before doing +
                    supersession of the outdated
CAS GATE            compare-and-swap advances (a git ref): the
                    provider's atomic refusal IS the fence — attempt,
                    and classify "moved" as a domain outcome
```

Everything upstream of a gate — pure computation, read-only discovery,
even expensive agent invocations that only *spend* — is **disposable**:
run it optimistically, and if authority moved while you computed,
discard it and let the fresh trigger restart the work. No checkpoints,
no partial-work salvage, no forcing. The gate refusing is the system
working.

## The idea

```text
[trigger] → disposable work … disposable work → GATE → world changed
                    │                            │
                    │ (authority moved)          │ (gate refuses: moved)
                    ▼                            ▼
                 discard                    "moved" exit → discard,
                                            wait for the new trigger
```

```python
# a subnet's exits say this out loud:
exits={
    "published": Port("published", Receipt),
    "discarded": Port("discarded", Discarded),  # work done, world untouched
}
```

Design consequence: place the gate as *late* as possible, keep
everything before it pure (concept 3's `disposable` bracket makes that
checkable), and let outdated-but-published artifacts stand when
harmless — an outdated comment is cheaper than a coordination
protocol.

## What it does not do

- No pre-flight authority checks racing the world: checking, then
  acting, then hoping is the pattern this replaces (attempt-first,
  concept 2).
- No transactional multi-gate commits: one gate per subnet exit path;
  if two world changes must cohere, the second is a new subnet
  triggered by the first's settled outcome.
- No rescue of interrupted pre-gate work — that is the point.

## Why trust it

ES-004 AX1 classified all 11 production activities into exactly these
two gate types; AX2 demonstrated the doctrine live (stale authority:
the agent ran, the fence caught it, `world.comments == []` — money
spent, world untouched); AX3 proved the CAS gate's outcome
classification as the staleness signal. The Navigator's ruling is
folded in: discard and restart; never force; outdated comments are an
accepted simplification.

## How it relates

- Concept 2 supplies identity, lookup-first, and classification.
- Concept 3's purity metadata makes disposability checkable.
- Concept 10 makes stale completions inert even when they arrive late.
