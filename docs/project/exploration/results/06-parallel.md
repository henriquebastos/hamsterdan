# 6 — Parallel

**Rely on this: parallel branches are named, the join is explicit and
total, and correlation comes from instance discipline — one engine per
case.**

## What it is

An AND-split runs named branches concurrently as independent token
flows; an AND-join waits for *all* of them and combines their results
into one aggregate token whose color names the combination. The join
is part of the combinator — visible in the net, never implied — and it
demands **totality**: every branch must be a block that always reaches
its exit, because a join over a branch that might not arrive is a
deadlock you authored.

## The idea

```python
par("gather",
    branches={
        "inventory": reserve(),      # names label the results
        "taxes":     calculate(),
    },
    returns=Quote,                   # the aggregate color, named
)
# downstream sees one token: Quote{inventory: Reservation, taxes: Taxes}

# racing variant — first result wins, the rest are drained visibly;
# refused unless every branch is pure (losing a side effect is a bug):
par_fail_fast("probe", branches={...}, returns=Answer, failure=Failure)
```

Duplicate and repeated tokens are safe because the join consumes
exactly one token per branch per instance — and instances never share
an engine: **one workflow case, one engine instance.** Cross-instance
joining is thereby structurally impossible, not checked-for.

## What it does not do

- No partial joins ("any 2 of 3") — never prototyped; do not assume
  it.
- No result combination logic inside the join — the aggregate is a
  named record of branch results; interpreting it is the next step's
  job.
- No racing over effectful branches, by refusal.

## How it relates

- Concept 3's totality and purity metadata are what the combinator
  checks.
- Concept 8: an effectful branch that can fail routes through the
  rail *before* the join, so the join's totality stays honest.
- Concept 10's epochs are the answer when "parallel" means overlapping
  *generations* of the same case, not branches of one generation.

## Why trust it

ES-003 AX4 proved split/join token flow, failure, duplicate-token, and
replay behavior on the real engine, plus the one-engine-per-case
correlation discipline; AX24 added named branches, the aggregate
color, join-policy explicitness, and the purity-gated race with
visible drains.
