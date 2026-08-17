# Marker-safe provider finding identity contract qualified locally

Fresh selected-V5
[`HBNetwork/demo-pr-readiness` PR 58](https://github.com/HBNetwork/demo-pr-readiness/pull/58)
passed all six jobs in
[Actions run 31991321091](https://github.com/HBNetwork/demo-pr-readiness/actions/runs/31991321091).
While the host was deliberately stopped, `henriquebastos` created the PR and
`crisbastos` submitted a distinct-human
[`CHANGES_REQUESTED` review](https://github.com/HBNetwork/demo-pr-readiness/pull/58#pullrequestreview-4948204540).
V5 restarted under the same explicit selector; seven relay deliveries entered
host custody immediately, all 14 eventual PR-specific webhook rows reached
terminal custody, and the
[App dashboard](https://github.com/HBNetwork/demo-pr-readiness/pull/58#issuecomment-5311473843)
landed.

The real provider operation completed with one accepted append and clean
runtime closure. Its response had the exact review envelope, three otherwise
structurally complete findings, and matching lineage, but every 15-character
finding ID contained a colon. Strict admission correctly returned
`RoundUnable(output_schema)` because the existing marker-safe grammar allows only
`[A-Za-z0-9][A-Za-z0-9._-]{0,47}`. No finding, repair, readiness, or Git effect
ran, and canonical History retained 743 records without Activity, firing, or
quarantine failure. PR 58 remains unchanged as the provider-output failure; it
was not retried or moved to another provider.

Review prompt version 3 now states that exact shared grammar for finding
identities and open-lineage references, explicitly forbids colons and
whitespace, and keeps every lineage reference unique. Conversation and coding
prompts remain version 2. The strict validator is unchanged and no provider
output is repaired or normalized. Retained version-2 review operations cannot
be silently reused under the changed prompt fingerprint.

Seventy-three focused agent protocol and Petrus runtime-host tests passed. The
project-wide checkpoint passed 1,169 Python tests, nine Bun relay tests, Ruff,
formatting, typing, and source/wheel builds. A fresh hero PR remains required for
live acceptance.
