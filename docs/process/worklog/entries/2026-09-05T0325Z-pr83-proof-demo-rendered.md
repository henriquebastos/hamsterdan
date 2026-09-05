# 1. PR83 proof demo rendered

The Navigator authorized a demo from the saved PR83 proof. A dedicated renderer
and sixteen-shot storyboard now produce a 148-second silent H.264 video at
1280×720 and 30 fps. The sequence covers the first summary, three native
findings, requested repair, App commit, clear rereview, resolved threads, human
approval, final readiness, and closure without merging.

The renderer checks the original and recovered proof manifests and each chosen
HTML/PNG hash before rendering. It reuses the existing caption strip, frame
geometry, reading-time rule, and crossfade duration. Source pixels remain at
1:1; captions stay below the evidence. The input manifests remain unchanged.

`bun run check` passed TypeScript and 115 tests with 272 assertions, zero
failures and no reported skips. All 48 start/middle/end previews were inspected
before rendering. The output passed ffprobe format checks and a complete decode.
The [demo manifest](../../../project/roadmap/cv19-private-v0-1-production/proof/pr83-demo-manifest.json)
records browser playback telemetry, visual review, and the output hash.

Review found no additional refactoring need or durable debt. Existing repeated
viewport-tile capture debt remains open; this presentation uses the verified
recovered screenshots. The movie preserves the source light/dark theme change,
compresses elapsed time, and inherits the documented recovery limits: later
assets, reconstructed root attributes, absolute dates, and the authorized
sign-in banner removal. It makes no new production claim.

No production or GitHub PR operation was needed. Generated media remains
ignored, with source and manifests committed. Navigator media acceptance and
durable publication remain pending; CV19 remains Active.
