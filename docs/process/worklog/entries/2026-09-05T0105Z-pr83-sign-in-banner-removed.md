# 1. PR83 sign-in banner removed from recovered views

The Navigator requested removal of the entire yellow "to join this conversation
on GitHub" div. All 21 recovered PR83 HTML files now omit that exact banner.
Embedded assets and the remaining markup were retained. The recovery CLI also
removes the banner, so subsequent regeneration preserves this presentation
choice.

All 21 updated pages rendered with zero external requests or broken images in
a fresh offline browser, and their regenerated online/offline screenshots match.
TypeScript passed. Two additional original-HTML regeneration attempts found
and removed the expected banner, then timed out waiting for remote assets to
reach network idle; full fresh-asset regeneration is not claimed. The delivered
21 pages reuse their existing embedded assets and passed the offline checks.
The all-clear page was independently opened offline and its footer inspected
after removal. No new tests or full release campaign were needed for this
presentation edit.

The [recovery manifest](../../../project/roadmap/cv19-private-v0-1-production/proof/pr83-html-recovery-manifest.json),
screenshots, index and archive were refreshed. Page heights now exclude the
banner. The original 131 proof files and archive retain their recorded hashes.
The README and proof narrative document this distinction; no runtime change,
deployment, new debt or broader refactoring was required. Local links, package
inventory, hashes and whitespace were checked before committing.
