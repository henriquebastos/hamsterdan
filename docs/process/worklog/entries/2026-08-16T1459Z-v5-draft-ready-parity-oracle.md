# V5 draft-to-ready parity oracle established

CV17.DS4.7 reconstructs the user-visible lifecycle behavior from historical
live PR 32 through independent production and V5 worlds. A signed draft-opened
webhook reaches terminal durable custody while GitHub remains silent: no
dashboard, readiness, finding, review, agent, rerun, or Git/ref effect. A
separate signed ready-for-review delivery is pending before admission, then
both topologies produce one clear exact-head review, one current dashboard, and
one ready advisory without mutation or merge work. Both deliveries settle
terminal and both worlds quiesce.

The oracle exposed a V5 draft dashboard effect and an ingress-ordering gap.
The provider-backed dashboard gate now returns typed `DashDeferred` under a
quiescent staged host grant. The outcome is a deliberate no-effect terminal,
not a provider fault; desired state, known landed state, and exact blocked or
faulted recovery custody remain actor-owned. Running work can publish the
current board, while a retried recovery still reissues its retained effect.

Petrus identified delivery commits each normalized fact but does not promise
which enabled transition the ordinary scheduler chooses next. The V5 runtime
now uses Petrus's public selection and driving policy seams to complete the
exact pure lifecycle fold for each accepted manifest row before admitting the
next row, while ordinary driving remains throughput-oriented. The boundary
fails closed rather than running unrelated work if the fold is unavailable.
Mailbox inspection also repairs an accepted-delivery/fold crash cut, while a
fully folded exact replay remains record-for-record inert.

Review-agent currentness now has a pre-custody boundary as well. A head round
whose staged authority already moved returns typed `RoundMoved` before request
custody, Agenticus route entry, or provider context reads. The review actor
restores its baton without emitting stale inability; ready admission opens the
current round. Genuine agent inability remains a typed fail-closed
`RoundUnable` outcome.

Focused host-ingress, dashboard, gate, V5-net, and complete topology-parity
checks passed. `scripts/check full` passed with 1,089 Python tests, nine Bun
relay tests, formatting, Ruff, typing, and source/wheel builds. Fresh explicitly
selected-V5 GitHub demonstrations remain mandatory for CV17 acceptance;
deterministic parity is intermediate evidence.
