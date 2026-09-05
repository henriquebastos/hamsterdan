# 1. PR83 presentation made consistently dark

The Navigator liked the PR83 video and requested dark mode throughout the
HTML, screenshots, and movie. The mixed appearance came from matching the
original capture themes: early states were light and later states were dark.
The embedded CSS already contained GitHub's explicit dark styles.

`live/pr83-dark.ts` changes only the recovered root `data-color-mode` from
`auto` to `dark`. It preserves every other source byte, including embedded
assets and saved content, and generates all 21 full-page screenshots offline.
Each page is checked under both light and dark browser preferences: identical
pixels, dark background and foreground, zero network requests, broken images,
scripts, or sign-in banners, and exact screenshot height. The original proof
and initial recovery remain unchanged as provenance.

The [dark manifest](../../../project/roadmap/cv19-private-v0-1-production/proof/pr83-dark-manifest.json)
binds those sources and outputs. The current demo storyboard consumes it,
retaining all sixteen shots, captions, crops, and durations. All 21 full-page
screenshots and 48 video previews were inspected. TypeScript and all 115 demo
tests passed with 272 assertions and no reported skips. The 148-second silent
H.264 output passed ffprobe and full decoding; the
[demo manifest](../../../project/roadmap/cv19-private-v0-1-production/proof/pr83-demo-manifest.json)
records the final playback review.

This is a presentation adjustment, with no production operations, provider
changes, or new durable debt. The existing capture-tile debt remains separate.
Navigator acceptance of the revised media and durable publication remain pending.
