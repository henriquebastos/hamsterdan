# Production provider drift failed closed; OpenAI custody corrected

The Navigator directed deployment of `main` at `def779618d19aa159186e7d0b536d26be4262d12`
on 2026-09-03. The clean release gate passed twice with 1,235 tests, the exact
`linux/amd64` candidate built and verified, and deployment qualification
reported `ok=17 changed=3` followed by `ok=17 changed=0`. Production remained
on revision `7e0abf65…` while the candidate was qualified.

Runtime provisioning first refused to replace the installed agent credential
because deployment authority resolved a different key. After the Navigator
authorized that replacement, provisioning completed and repeated unchanged,
but the candidate then failed closed at startup: the retained Pi A2 state was
bound to `openai/gpt-5.6-sol`, while the new production and operations templates
declared `anthropic/claude-sonnet-4-5`. The service was stopped immediately.
The prior credential, generated environment, and systemd unit were restored;
revision `7e0abf65…` returned active with zero restarts, and `/healthz` reported
one configured, reconciled, and active installation, one active repository, all
96 inbox rows terminal, no runnable hints, and no degraded scheduler instance.

The Navigator chose to preserve the existing OpenAI identity. The exact
working production credential was streamed from the VM into the new
`hamsterdan-ops/openai` item without printing or local persistence and verified
byte-for-byte. `env-ops.tpl` now selects that item, while `env-prod.tpl` declares
`openai/gpt-5.6-sol`. The deployment tests encode the matching route and the
opposite-provider refusal. The focused deployment suite passed 12 tests; the
full release gate then passed both its parallel and serial runs with 1,235 tests
each. A real operations-environment construction resolved OpenAI, one account,
and one repository without exposing authority values.

The corrected candidate still requires accepted history before it can be built
from a clean revision and deployed. Production remains healthy on the restored
revision until that cutover.
