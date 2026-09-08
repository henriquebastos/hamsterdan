# 1. Production deployed and PR85 exercised

Production runs Hamsterdan `1eef74a` with Petrus HEAD pinned to `913acb0`.
The exact image includes the package license and passed canonical verification.
Candidate qualification and runtime provisioning repeated with zero changes.
All 21 previous PR histories remain unchanged; the stopped backup and rollback
image remain available.

[PR85](../../../project/roadmap/cv19-private-v0-1-production/proof/pr85.md)
completed initial summary, three findings, App repair, six green jobs on both
heads, clear rereview, automatic thread resolution, human approval, and one
readiness advisory. Both inspectors passed all ten checks. The PR was closed
unmerged. Its 2,688-record final History replayed without effects and contained
40 completed Activities with none failed or pending. Final production health
was `ok`, with all 743 inbox rows terminal and zero automatic restarts or
scheduler errors.

Two findings remain open. A conversational status reply described approval
before a human approved; the changes-requested gate still prevented readiness.
An older unverified Pi cleanup record caused shutdown errors on both the old
release stop and new release restart. The service returned healthy, and all ten
new demo operations cleaned up successfully. Neither finding was fixed or
accepted as deferred debt. The linked proof records diagnosis, evidence hashes,
and capture limits. Existing media acceptance, broader monitoring, candidate
retention, and remote Amp migration work remain open.
