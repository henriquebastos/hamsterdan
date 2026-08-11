# Legacy Amp agent execution removed

Hamsterdan removed the rollback-only Amp subprocess runner and made isolated
Agenticus/Pi its sole agent execution architecture. Host startup now resolves
one exact non-null profile/snapshot composition, probes one owned Pi runtime,
and fails closed when that runtime is unavailable. Durable route custody retains
only the exact profile/snapshot identity needed for retries and restart.

The prior route schema migrates during activation after terminal History repair:
valid unresolved Agenticus work survives exactly, settled legacy rows disappear,
and unresolved legacy or unreconstructible Agenticus work fails atomically
without reinterpretation. Retired mode/isolation settings fail explicitly.
Provider-neutral result validation tests moved out of the deleted Amp adapter
portfolio. The separate Amp GitHub webhook relay was unchanged.

Focused Agenticus, Pi, protocol, Activity, service, and migration evidence passed
140 tests. Quick and full static/type/format/package gates passed; all 9 Amp
webhook relay tests passed and the Python suite passed 584 tests. Adversarial
review found and drove correction of migration ordering and protocol-test
ownership, then returned `APPROVE`. No Net, lifecycle, Motus, scheduler, GitHub
ingress, or Petrus behavior changed.
