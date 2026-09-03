# Demo-video agent instructions

This directory contains a reproducible Remotion studio and a separate public
GitHub live-capture lane. Before changing either lane or rendering an artifact,
read `README.md` in full. Its artifact policy is shared. The creative and
cadence contracts apply to synthetic Remotion work under `src/`; they do not
authorize overlays or reconstruction in `live/`.

## Starting a scenario

- Begin with the scenario worksheet in `README.md`.
- Copy `src/scenarios/template.tsx`; use `src/scenarios/pr47-hero.tsx` as the
  complete reference for dashboard-rail and message-feed behavior.
- Keep scenario copy under `src/scenarios/`. Reuse `src/components.tsx` and
  `src/timing.ts` instead of creating scenario-local substitutes.
- Register each deliverable composition in `src/root.tsx` with a distinct ID.
- Use guide and main-message text—not dashboard metadata or decorative
  labels—to establish initial timing.

## Required production sequence

1. Run `bun run check`.
2. Render representative stills for every act, guide change, and dense card
   arrival before starting a full render.
3. Inspect the stills for clipping, hierarchy, dashboard causality, and native
   review-thread fidelity.
4. Render the full candidate only after the checkpoints are sound.
5. Strip any nominal audio stream and verify the encoded file with `ffprobe`.
6. Watch or inspect the entire encoded video at normal speed. Static frames are
   not sufficient evidence for cadence or transition quality.

Do not commit `output/`, checkpoint images, MP4 files, `node_modules/`, or
temporary media. Approved videos belong in a GitHub Release or durable media
store; their reproducible source belongs here.

## Live GitHub capture

- Keep `live/` anonymous, public-only, nonpersistent, and read-only.
- Validate all declared provider-visible evidence before publishing media.
- Never add an authenticated fallback, storage state, profile directory,
  cookies, tokens, arbitrary selectors, page scripts, or mutation-capable UI
  actions.
- Render only hash-verified browser screenshots in manifest order. Do not use
  Remotion, overlays, or synthetic browser chrome.
- The montage renderer (`live/render.ts`) stays literal: no captions, no
  transitions, no interpolation. The transition renderer
  (`live/transition-render.ts`) may crop those same stills at 1:1, crossfade
  between two of them, and add one caption strip below the evidence pane. Its
  caption text must come from the manifest, never from new prose, and no other
  authored pixel may appear.
- Keep every checkpoint's three evidence layers: before and after DOM HTML, a
  full-page PNG verified against
  `max(document.body.scrollHeight, document.documentElement.scrollHeight)`, and
  the montage assembled from those stills. Never add PDF output.
- Record each checkpoint's target-element anchor box in document coordinates.
  A static journey has no meaningful pixel diff, and the anchor is the only
  thing that can frame it honestly.
- A watched journey (`live/watch.ts`) reuses the same anonymous, nonpersistent,
  read-only context and records one numbered state each time the watched page's
  visible content changes. It fails closed on repository, pull-request-state,
  actor, and challenge-page drift exactly like the checkpoint lane.
- Do not hand a pending Playwright-backed promise to `expect(...).rejects`;
  bun:test settles it about one second per browser round trip. Settle the
  promise first, then assert on the error.
- Run acceptance capture from a clean committed revision, inspect every PNG,
  and watch the complete encoded montage once.
