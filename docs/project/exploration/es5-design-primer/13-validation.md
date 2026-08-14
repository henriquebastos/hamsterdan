# 13 — Validation

**Rely on this: four rungs, each catching what the others cannot — and
descent below the algebra swaps in a stricter law, never a weaker
one.**

## What it is

Validation is a ladder, not a gate. Each rung caught real bugs the
others missed, in the experiments themselves:

```text
1 EDIT TIME      the type checker rejects most composition mistakes in
                 the editor, from source text alone — no execution
2 COMPOSE TIME   eager refusals at the combinator call site; the message
                 names the offending element and, often, the fix verbatim
3 COMPILE TIME   soundness: every node on some entry→exit path; declared
                 contexts exempted; undeclared ambient state refused
4 MOTION TIME    bounded driving: the only rung that can catch
                 data-driven residue (undeclared runtime outcomes,
                 non-termination) — opt-in, never a side effect of review
```

Rung 1 works best when ports are *inferred from signatures* — declaring
a port twice creates the one hole the checkers share, so inference is
safer than declaration. Rungs 2–3 are deterministic and remain the
final authority; checkers advise.

The same ladder is a **machine feedback loop**: a code generator's
candidate source goes through a total `review` that returns structured
feedback (stage, message, offending line) without ever executing the
net — proven by poisoning the engine and reviewing anyway.

## Descent

When the algebra genuinely cannot say it, descend — under a two-depth
law, both depths governed:

```text
IN-BLOCK      hand-build a Block from raw nodes (per-arc value filters,
              weights, same-colored exits): still governed by rungs 2–4,
              still runs through the ordinary run surface
BELOW-BLOCK   constructs that would break what a block MEANS (the
              inhibitor arc is non-flow): splice at net level; soundness
              governs the block part first, the kernel's shape law
              governs the union; the run surface is honestly manual
```

The refusal boundary is semantic — an inhibitor inside a block is
refused *because* entry→exit reachability would stop meaning anything.

## What it does not do

- No rung proves termination or purity; loops are bounded at motion
  (concept 7), purity is declared (concept 3).
- Review executes the authoring source (composition is ordinary
  Python) — extend it the trust you extend the source; the editor rung
  is the no-execution alternative.
- Descent never bypasses a rung; it changes which law applies.

## How it relates

- Concept 4's fusion refusals are rung 2's core.
- Concept 14's bounded run is rung 4.
- Concept 15's checklist ends with "which rung would have caught this
  mistake?"

## Why trust it

ES-003 AX26 pinned the editor rung (8/9 mistakes rejected, zero false
positives, inference closing the shared hole); AX27 measured
repair-grade messages (5/10 carry the fix verbatim) and proved
review-never-executes behaviorally; AX22/AX23 own rungs 2–3; AX28's
advance budget is rung 4; AX29 proved the descent seam with no check
weakened. ES-004 AX11 confirmed the editor rung on unmodified
production models with the CI checker already in place.
