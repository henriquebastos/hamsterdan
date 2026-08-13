# ES-004 experiments

One experiment per file, `ax<N>-<slug>.md`. Later experiments should
emerge from findings; only the opening arc is planned.

| ID | Question | Status |
| --- | --- | --- |
| [AX0](ax0-experience-map.md) | What is the topology-independent experience map derived from boundary evidence alone? | concluded — promising; continue |
| [AX1](ax1-subnet-contracts.md) | Which concerns form subnets with secure entry/exit contracts? | concluded — promising; continue |
| [AX2](ax2-linear-review.md) | Can one mostly pure/disposable concern be expressed as a linear ES-003 block chain? | concluded — promising; continue (spike: [ax2-linear-review/](ax2-linear-review/)) |
| [AX3](ax3-attempt-first.md) | Attempt-first gates: is the operation itself the fence, and does dropping pre-checks simplify the subnets? | concluded — promising; continue, AX1 amended (spike: [ax3-attempt-first/](ax3-attempt-first/)) |
| [AX4](ax4-typed-port-composition.md) | Do two subnets compose through typed named ports without a shared control place? | concluded — promising; continue (spike: [ax4-typed-port-composition/](ax4-typed-port-composition/)) |
| [AX5](ax5-divergence-sweep.md) | Where does the independent model diverge from `topology.py`, and is each divergence accidental complexity, a missed requirement, or an open choice? | concluded — question answered; 73% of read arcs ACCIDENTAL, projection OPEN, MISSED list explicit (spike: [ax5-divergence-sweep/](ax5-divergence-sweep/)) |
| [AX6](ax6-unified-quiescence.md) | Are draft dormancy, provisional head, and supersession one general quiescent state with one resume move? | concluded — promising; continue (spike: [ax6-unified-quiescence/](ax6-unified-quiescence/)) |
| [AX7](ax7-orthogonal-conversations.md) | Are conversations orthogonal to the head machine, making AX6's Hold unnecessary? | concluded — promising; continue, AX6 Hold dissolved (spike: [ax7-orthogonal-conversations/](ax7-orthogonal-conversations/)) |
| [AX8](ax8-projection-fold.md) | Is the readiness projection's 25-read-arc join a requirement or a mechanism — can a fold over typed concern exits preserve every production rule? | concluded — promising; continue, AX5's C4 OPEN closed as ACCIDENTAL (spike: [ax8-projection-fold/](ax8-projection-fold/)) |
| [AX9](ax9-timer-ingress.md) | Is time a special citizen requiring marking-wide reads, or one more provider whose `TimerDue` facts fold into the snapshot? | concluded — promising; continue, reminder's 9 reads join the ACCIDENTAL class, Petrus Delay purity kept as time-as-fact (spike: [ax9-timer-ingress/](ax9-timer-ingress/)) |
| [AX10](ax10-actions-repair-loop.md) | Is the rerun → repair loop real domain structure, and can a phase-explicit ladder with attempt/fingerprint fences express it without flags, the basis place, or read arcs? | concluded — promising; continue, the ladder is REQUIREMENT, its mechanism ACCIDENTAL; AX5's MISSED list closed (spike: [ax10-actions-repair-loop/](ax10-actions-repair-loop/)) |
| [AX11](ax11-payload-shape.md) | What does a port contract carrying payload shape look like — fusion rule, adapters, guard fields — and how much do pyright and ty enforce at edit time? | concluded — promising; continue, nominal fusion + shape-as-diagnostic; ty catches all shape mistakes today (spike: [ax11-payload-shape/](ax11-payload-shape/)) |
| [AX12](ax12-human-fold.md) | Is the human concern "structurally like actions", or a different shape — and how do observation snapshots and durable notes coexist? | concluded — promising; continue, it is a mirror plus notes, no ladder; the reassign/observation clobber surfaced as a new OPEN (spike: [ax12-human-fold/](ax12-human-fold/)) |

AX6 and AX7 ran before AX4/AX5: AX6 fell directly out of AX3's
conclusion (the operation is the fence, so what is `provisional` still
for?) plus Navigator direction on unifying dormancy; AX7 fell out of
AX6's one open question (held conversations). AX4 then composed the
settled pieces, and AX5 closed the planned arc with the executable
divergence sweep. AX8-AX12 then worked AX5's MISSED list: the
readiness projection/announcement gate (AX8), timers and reminders
(AX9), the actions rerun/repair loop with lineage through confirmed
resumes (AX10), payload shape contracts (AX11), and human observation
folding (AX12). Every executable MISSED item is now spiked. Still open
for the Navigator, as product choices rather than spikes: finding
lineage through quiescence (AX5 #6) and the reminder-recipient
ownership collision AX12 surfaced (provider snapshot vs local note).

Divergence classification vocabulary for AX5:

```text
ACCIDENTAL  — complexity in the current net not demanded by the experience
MISSED      — a real requirement the independent spec failed to capture
OPEN        — a genuine design choice with no boundary-evidence winner
```
