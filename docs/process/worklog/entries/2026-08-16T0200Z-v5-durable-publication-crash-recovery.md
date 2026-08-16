# V5 durable publication crash recovery completed

CV17.DS3 began with the durable reply, dashboard, and readiness-announcement
worker boundary. Each publication now has one globally identified Motus
attempt. A worker killed after claim converges on restart from LocalDispatch's
frozen `DeadlineExceeded` fact to the actor loop's existing typed blocked
terminal. The original occurrence is terminal and remains blocked until an
authorized human recovery creates one fresh occurrence with the same provider
identity and exact retained request. Unknown failures remain loud.

The recovery portfolio uses real SQLite claim expiry and JSONL History reload
for all three publication gates, including stable repeated restart and explicit
recovery. `scripts/check full` passed with 1,015 Python tests, nine Bun relay
tests, formatting, Ruff, typing, and source/wheel builds. Oracle boundary review
returned `clear to commit`. CV17.DS3 remains active for inline effects and the
remaining host custody restart portfolio.
