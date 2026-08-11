# DS11 bounded setup orchestration qualified locally

The hardened CV16.DS11 setup boundary is now composed into one production-owned
`qualification-setup` operator command. Credential and exact target custody
enter only through private mode-`0600` files; no token, coordinate, ref, PR, or
CAS value is accepted as a CLI argument. The command excludes ambient authority,
admits the declared PAT only in its bounded child environment, verifies exact
authenticated account and repository identities plus public/active/empty/write
state, and repeats target/ref admission immediately before mutation.

`AtomicSetupPush` remains the sole mutation boundary. It durably spends before
one exact non-forced atomic push of the deterministic base and child refs. An
attempted or uncertain result receives at most one complete exact readback and
can never retry. Only a readback containing exactly the two expected refs admits
read-only PR/current-CAS/stale-CAS observations. First cause and cleanup
uncertainty remain separate, fixed-shape evidence retains no caller-controlled
text, and managed credential, coordinate, fixture, HOME, and GitHub configuration
material is removed while the durable marker survives.

The credential-free integration portfolio performs actual accepted and rejected
atomic pushes against local bare repositories and covers timeout before and
after spend, exact readback, zero retry, downstream suppression, current/stale
observation behavior, restart refusal, strict ref parsing, environment isolation,
cleanup uncertainty, and secret/coordinate diagnostic canaries. After
reconciliation with current `main`, 114 focused tests and the read-only existing
demo preflight pass. The full gate passes formatting, Ruff, ty, nine Bun tests,
source and wheel builds, and 562 Python tests with one provider test deselected.
No DS11 credential, target, cleanup, provider, paid call, remote mutation, or
DS12 operation occurred. DS11 remains Qualified Locally and live support remains
unaccepted.
