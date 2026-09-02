# What Hamsterdan is

Hamsterdan is a GitHub App that answers one question on every pull request it
watches: **is this PR ready to merge?** It never merges. Humans keep that
power; Hamsterdan does the watching, the chasing, and the fixing so humans only
decide.

You put a repository on its watchlist. From then on, every GitHub webhook lands
in the webhook inbox first, and intake feeds each event exactly once into that
pull request's own PR workflow, a Petri net built on Petrus. One workflow per
PR identity, alive from first event to close.

The workflow is nine subnets running at the same time, each keeping its own
notebook about the PR:

1. **Lifecycle** tracks the head commit and draft/ready/closed, and starts a
   new generation on each fresh start.
2. **CI** watches the check runs for the current commit.
3. **Escalation** handles CI failure with a fixed budget: re-run the failed
   jobs once, then send a coding agent to fix it once, then hand it to a human.
4. **Review** runs one AI code review per generation and posts the findings.
5. **Push** writes commits to the PR branch, whether an agent fix, a base
   update, or a conflict resolution, one at a time, never clobbering a human's
   push.
6. **Conversation** reads human comments addressed to the bot and replies or
   acts.
7. **Summary comment** keeps one comment edited in place with where every
   requirement stands.
8. **Reminders** nudges when the PR sits idle.
9. **Readiness** posts the ready comment, once per generation, when every
   requirement is met: checks green, findings resolved, approvals present, no
   unresolved threads, base current.

Every write to GitHub is an activity: queued durably, run by a worker, guarded
by a staleness check so a PR that moved on is never touched by a stale request.
Every step is a recorded checkpoint, so the process can be killed at any moment
and resume without double-posting a comment or losing a decision. The GitHub
App token never leaves the server; coding agents work on credential-free
checkouts and the server makes the actual push.

Hamsterdan exists to prove that Petrus makes this kind of always-on,
crash-safe, multi-actor coordination something one person can build, read, and
explain.

Every term above is defined in the [project glossary](../project/glossary/index.md).
