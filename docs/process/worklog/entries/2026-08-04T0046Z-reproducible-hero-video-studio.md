# Reproducible hero video studio committed

The accepted PR47 journey now has a reproducible Remotion production studio at
`tools/demo-video/`, committed in
[`942112a`](https://github.com/henriquebastos/hamsterdan/commit/942112a).
The source preserves the 1920×1080, 30 fps, 179-second silent presentation,
including the novice-oriented story guide, native review-thread cards, shared
message column, dashboard rail and semaphore, collaborator colors, and
text-driven cadence.

The studio records the settled creative and QA contracts, provides a compilable
scenario template, and implements the default reading estimate of 3.8 words per
second with minimum holds, transition margin, and guide lead. Repeatable scripts
render checkpoint stills and the final H.264 file, remove Remotion's nominal
audio stream, and inspect the encoded result with `ffprobe`. Generated images
and MP4 files remain outside Git and belong in a release or durable media store.

Project-orb setup now installs missing media tools, syncs the locked Bun
environment, and ensures Remotion's rendering browser. The setup converged on
repeated runs in under one second with warm caches; resume remained immediate.
A clean non-interactive login shell found uv, Bun, FFmpeg, FFprobe, ImageMagick,
and the Remotion browser, and the video TypeScript check passed. Scoped agent
instructions require future threads to read the production contract, render
checkpoints before a full candidate, and inspect the complete encoded video.
