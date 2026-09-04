# 1. PR78 discarded and reply custody reproduced

[PR #78](https://github.com/HBNetwork/demo-pr-readiness/pull/78) passed the
opening strict inspector's ten checks. Review `5117731031` contained exactly
three App inline findings at `gate.py:10`, `gate.py:16`, and `cache.py:11`.
History recorded `AgentReview` at occurrence 89 and `ReviewLanded` at 91.
After Cris requested changes and the author requested repair, the App published
commit `15ce3c81ef549c2667210fa43446b2e91deae7c8`; all six CI jobs passed.
The reply Activity at occurrence 207 nevertheless completed as `ReplyBlocked`
after mutation occurrence 212 completed as `Pushed`. The run was discarded and
closed unmerged before approval, as required by the campaign's clean-History
rule. The [capture manifest](../../../project/roadmap/cv19-private-v0-1-production/proof/pr78-manifest.json)
records local artifacts, hashes, and omissions. This is failure evidence, not
a completed production proof package.

The application composed replies with the same strict current-authority reader
used by review and mutation. A completed repair moves GitHub's head before the
new webhook can be staged, so that reader rejects an otherwise valid immutable
acknowledgement before any comment POST. Two deterministic reproductions cover
the head mismatch alone and the same mismatch with a pending webhook. Replies
now use their persisted admitted context; the existing operation-scoped lookup
still prevents duplicate replies across heads. Review and mutation retain the
strict reader, and the host's revoked-route protection remains in place.

Before release qualification or deployment, the existing production publisher
was exercised manually on the closed PR. One App-authenticated POST returned
201; repeating the exact operation recovered the same comment before consulting
context. The independent GitHub read identifies
[comment 5546416889](https://github.com/HBNetwork/demo-pr-readiness/pull/78#issuecomment-5546416889).
No deployment was used to discover provider behavior.

Unattended SSH initially failed because OpenSSH asked the local 1Password SSH
agent to sign despite the supplied temporary private-key file. Disabling that
agent with `IdentityAgent=none` made the same operations service-account route
work without a fingerprint prompt. The new `deployment.observe` command
successfully exported 1,715 History records, 14 dispatch rows, 30 inbox rows,
and host health for PR78. It filters metadata without exporting Activity or
webhook payloads. The last captured production health was `ok` with no scheduler
error classes; the service remained on the prior revision at this checkpoint.

`scripts/check release` passed 1,253 tests in parallel and 1,253 serially with
18 declared platform deselections. The two acknowledgement cases failed before
the fix and passed afterward. The inspection and SSH tests passed nine cases,
including excluded-payload canaries, read-only store checks, schema rejection,
and symlink rejection. Ariad links and evidence-manifest hashes were checked.
