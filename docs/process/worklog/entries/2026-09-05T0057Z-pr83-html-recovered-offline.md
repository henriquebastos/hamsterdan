# 1. PR83 HTML recovered and verified offline

The Navigator requested the HTML capture defect be fixed, then limited
historical recovery to PR83. All 21 PR83 HTML files now have self-contained
derivatives. The maintained capture and watch paths embed CSS, nested images
and fonts, preserve the document root and rendered shadow DOM, remove scripts,
and freeze automatic color-scheme rules to the captured preference. Missing
resources fail capture. Recovery uses the original saved DOM, reconstructed
root attributes and newly fetched public assets; it does not replace earlier
PR states with today's closed page.

Code commits are `1225895` and `f83fa9d`. The latter identifies the committed
tooling used for the final recovery. The
[recovery manifest](../../../project/roadmap/cv19-private-v0-1-production/proof/pr83-html-recovery-manifest.json)
binds 95 local files and a separate tar archive. Start at
`tools/demo-video/output/proof/html-recovery-20260905/index.html`.
PR80 recovery outputs were removed when the Navigator narrowed scope.

## 1a. Verification and experience

1. The original serializer failed the external-stylesheet offline regression.
   The fixed implementation passes nested CSS/image/font, shadow DOM, opposite
   theme preference, unchanged live-page pixels and missing-resource tests.
   `bun run check` passes all 112 media tests and TypeScript, with no skips.
   The final recovery CLI adjustment also passed TypeScript and all 21 real
   historical reconstructions.
2. Each recovered page opened in a fresh offline browser with zero network
   requests, broken images or scripts. All 21 offline screenshots exactly match
   their restored online counterparts. The recovery command fails when those
   pixels differ. All 21 retain their original screenshot dimensions.
3. All nine distinct rendered states were visually inspected. Accepted original
   PNG comparisons are recorded separately; rejected tiled PNGs 06 and 17 were
   excluded as references. Remaining differences include absolute timestamps
   and small browser rasterization differences. Historical pixel identity is
   not claimed.
4. An independent anonymous `agent-browser` session opened the actual all-clear
   file with networking disabled and a light preference. The page retained its
   dark background, Mona Sans font, all 19 images and zero scripts. The index
   was also opened and visually inspected offline.
5. The original 131 PR83 files and original archive still match all 132 recorded
   hashes. Production, provider selection and the completed hero result are
   unchanged. This work required no deployment or GitHub PR mutation.

## 1b. Review, debt and coherence

Review kept resource parsing in the pinned SingleFile Core dependency and
shared the capture implementation across both maintained lanes. Visual
verification caught a CSSOM serialization defect in variable-based border
shorthands; theme freezing now changes only parsed media-condition ranges.
No broader refactoring was required.

The HTML packaging debt is resolved for the maintained tooling and requested
PR83 recovery. Uncaptured historical relative-time shadow content remains an
explicit limit. The separate repeated-tile screenshot debt and CV19 media
acceptance remain open. The README, debt ledger, CV19 status, original proof
manifest link and this worklog agree on these boundaries. Documentation links,
artifact hashes and whitespace were checked before the history action.
