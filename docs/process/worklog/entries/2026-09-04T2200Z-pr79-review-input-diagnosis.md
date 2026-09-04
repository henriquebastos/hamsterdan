# 1. PR79 discarded after incorrect cache anchors

The reply-custody correction completed release qualification and deployed as
`e3a79bbfc839596f2dacec1db820efb18b159a3b`, image
`sha256:639862775b0c22ff65ac579f3b212fb95cbbee678f41cb3f413b713836941e0e`.
Deployment and provisioning repeats both reported `changed=0, failed=0`.
Production remained active with zero restarts and healthy scheduler status.
All operations used the operations service account and fingerprint-pinned SSH
with the local SSH agent disabled; no interactive fingerprint was needed.

[PR #79](https://github.com/HBNetwork/demo-pr-readiness/pull/79) opened at
`aab4140e819bb4b0247ca6eb831d41bece7467fa` and passed all six CI jobs. Its
History contained `AgentReview` and `ReviewLanded` without an error terminal.
Review `5117962621` published exactly three App inline comments, but the cache
finding targeted line 10 and related line 5 instead of statements 11 and 6.
The strict inspector failed two of ten checks. The PR was closed unmerged
before any human review or repair request. The
[failure manifest](../../../project/roadmap/cv19-private-v0-1-production/proof/pr79-manifest.json)
records the captures and offline export. This discarded run does not establish
that the reply correction completes a clean journey.

The exported tool calls show repeated failed reads of `diff.patch`. The review
request advertises this file, but the exact-head workspace previously exported
only tracked repository files. The agent used unnumbered source after those
failures and reported the two incorrect cache anchors. A local Git regression
reproduced the missing input. Review preparation now materializes the requested
merge-base diff and a companion containing changed head files with numbered
source lines, including blanks. The review instruction requires copying exact
anchors from that companion. Existing repository files at either input path
cause a bounded preparation failure rather than being overwritten. Coding
workspaces and their mutation authority are unchanged.

Before release qualification or deployment of this correction, a manual call
through the existing production OpenAI/Pi tool boundary read numbered cache
source and identified primary line 11 and related line 6. No GitHub authority
was supplied to the agent. The strict inspector and its expected findings were
not changed. The captured manual result is part of the manifest.

The read-only runtime observer proved useful for correlating History, dispatch,
inbox custody, and service health. Detailed diagnosis still required the
existing durable transcript exporter; raw webhook payloads were deliberately
excluded under the Navigator's explicit instruction. Three cancelled deferred
agent operations have no session, which the export reports as gaps. The
settled review's session, review requests, History, boards, and normalized inbox
were captured. Missing blocked-publication reasons remain tracked debt.

`scripts/check release` passed 1,256 tests in parallel and 1,256 serially with
18 declared platform deselections. The missing-file regression failed before
the correction and passed afterward; both repository-file collision cases pass.
The source changes are confined to review preparation and its instructions.
Manifest hashes, changed Ariad links, and diff whitespace were checked. No new
architectural abstraction or unresolved implementation debt was introduced.
