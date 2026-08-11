# Petrus speculation ledger

Potential Petrus runtime changes suggested by ES-003 authoring-model
experiments. Petrus stays frozen at
`3b41f19aa68ed228e68324f7c6888371f805b560` throughout the series; entries
here are analysis outputs for possible future Petrus-lane work, each tied to
the experiment evidence that motivated it. Nothing here is a commitment, and
no experiment may depend on a speculated change.

Ruling (Navigator, 2026-08-11): Petrus is considered frozen for the
experiments, but speculation about runtime changes is welcome as a dependent
result of the explorations.

## Entries

### SP-1 — Bind real types instead of nominal color strings

- Raised by: Navigator, 2026-08-11 (series setup).
- Today: `type Color = str`; the authoring DSL accepts a Python class but
  stores only `cls.__name__`. No registry maps colors back to classes;
  replay yields generic `Token(color, data)` and hydration is the
  application converter's job. Arc admission is nominal string equality
  (`Arc.admits`), so subclassing, unions, and generics are invisible to
  the runtime.
- Speculation: places/arcs could carry type objects (or a color registry)
  so admission, hydration, and validation share one authority; subtype and
  union admission would become runtime semantics instead of authoring-layer
  convention.
- Watch in: AX3 (inference over annotations), AX5 (union/subtype routing),
  AX7 (type + guard hybrid). These experiments will show precisely where
  nominal string identity forces the authoring layer to compensate.
- Constraints any proposal must respect: the net definition stays
  language-neutral and serializable (`NetDefinitionV3` carries portable
  names, never implementation objects); history replay must not require
  importable domain classes.
- AX3 evidence (2026-08-11): nominal identity held up better than
  expected for inputs — the typed derivation already refuses same-color
  fan-in loudly, and place-bound ports resolve it entirely above the
  runtime. The genuine nominal-string casualties observed: unions have
  no color (`Approved | Rejected` must be exploded by the compiler,
  AX5), and generics erase (`list[Decision]` → `"list"`), forcing
  wrapper dataclasses.

### SP-2 — First-class sinks (no-output activities)

- Raised by: AX3 probe, 2026-08-11.
- Today: `DerivedActivityHandler` requires the result annotation to match
  at least one output arc color, so `-> None` activities fail derivation
  (`return type NoneType matches no output arc`). A place explicitly
  colored `"NoneType"` satisfies it mechanically — workable but it leaks
  a Python spelling into the language-neutral net and creates a
  token-per-completion place the author never wanted.
- Speculation: either the derivation layer accepts a declared "no
  projection" sink, or a canonical completion color exists. Until then
  the AX compiler can emit the `NoneType` completion place and hide the
  ugliness above the runtime.
- Watch in: AX4 (join branches whose sides produce nothing), AX8
  (retry exits), AX11 (real fragment).
