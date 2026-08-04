# Demo-video agent instructions

This directory is a reproducible Remotion studio for guided Hamsterdan scenario
videos. Before changing a scenario or rendering an artifact, read `README.md`
in full. Its creative contract, cadence contract, artifact policy, and QA
checklist are requirements unless the Navigator explicitly changes them.

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
