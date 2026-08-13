# ES-004 experiments

One experiment per file, `ax<N>-<slug>.md`. Later experiments should
emerge from findings; only the opening arc is planned.

| ID | Question | Status |
| --- | --- | --- |
| [AX0](ax0-experience-map.md) | What is the topology-independent experience map derived from boundary evidence alone? | concluded — promising; continue |
| [AX1](ax1-subnet-contracts.md) | Which concerns form subnets with secure entry/exit contracts? | concluded — promising; continue |
| [AX2](ax2-linear-review.md) | Can one mostly pure/disposable concern be expressed as a linear ES-003 block chain? | concluded — promising; continue (spike: [ax2-linear-review/](ax2-linear-review/)) |
| [AX3](ax3-attempt-first.md) | Attempt-first gates: is the operation itself the fence, and does dropping pre-checks simplify the subnets? | concluded — promising; continue, AX1 amended (spike: [ax3-attempt-first/](ax3-attempt-first/)) |
| AX4 | Do two subnets compose through typed named ports without a shared control place? | planned |
| AX5 | Where does the independent model diverge from `topology.py`, and is each divergence accidental complexity, a missed requirement, or an open choice? | planned |
| [AX6](ax6-unified-quiescence.md) | Are draft dormancy, provisional head, and supersession one general quiescent state with one resume move? | concluded — promising; continue (spike: [ax6-unified-quiescence/](ax6-unified-quiescence/)) |

AX6 ran before AX4/AX5: it fell directly out of AX3's conclusion (the
operation is the fence, so what is `provisional` still for?) plus
Navigator direction on unifying dormancy. AX4/AX5 remain planned, and
AX6's divergence table feeds AX5.

Divergence classification vocabulary for AX5:

```text
ACCIDENTAL  — complexity in the current net not demanded by the experience
MISSED      — a real requirement the independent spec failed to capture
OPEN        — a genuine design choice with no boundary-evidence winner
```
