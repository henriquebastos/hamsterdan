# Hamsterdan demo-video studio

This Remotion project turns a completed GitHub scenario into a guided,
presentation-style product video. It preserves the approved PR47 hero journey
and the production rules needed to reproduce it or create another scenario
without reconstructing the creative brief from conversation history.

The rendered MP4 is a generated release asset. Source, scenario copy, timing
rules, avatars, and render commands live here in Git.

## Reproduce PR47

Requirements: Bun, Chromium dependencies supported by Remotion, `ffmpeg`, and
`ffprobe`. ImageMagick's `montage` is optional for contact sheets.

In an Amp project orb, committed `.agents/setup` installs these tools, syncs
this directory from `bun.lock`, and prepares Remotion's rendering browser. A
fresh thread should not require manual installation. Outside an orb, install
the requirements and run the locked Bun install yourself.

```sh
cd tools/demo-video
bun install --frozen-lockfile
bun run check
bun run stills:pr47
bun run render:pr47
```

The render is written to:

```text
tools/demo-video/output/hamsterdan-pr47-hero.mp4
```

Expected properties are 1920×1080, 30 fps, H.264, 179 seconds, and no audio
stream. `output/` and `node_modules/` are intentionally ignored.

Use `bun run studio` for interactive timing work. The canonical composition is
`PR47Hero`; its scenario source is `src/scenarios/pr47-hero.tsx`.

## Create another scenario

1. Collect the stable GitHub story: PR creation, comments, native review
   threads, checks, confirmations, commits, approvals, and terminal outcome.
2. Write a six-to-eight-line plain-language narrative for a viewer meeting
   Hamsterdan for the first time.
3. Copy `src/scenarios/template.tsx` to `src/scenarios/<slug>.tsx`.
4. Copy `pr47-hero.tsx` only when the new scenario needs the complete dashboard
   rail and feed behavior. Replace story copy and states before tuning motion.
5. Register the composition in `src/root.tsx` with a unique ID and duration.
6. Derive initial event spacing with `readingFrames`, `nextBeatFrame`, and
   `eventAfterGuideFrame` from `src/timing.ts`.
7. Render checkpoint stills across every act before paying for a full render.
8. Render the video, remove nominal audio, inspect the complete file, and store
   the approved MP4 as a GitHub Release asset or in durable media storage.

Do not use live GitHub page height or browser scrolling as the presentation
model. Reconstruct the observed events as cards so the viewer's focus follows
the story rather than the page.

## Creative contract

These are settled defaults. Change them intentionally, not accidentally.

### Narrative

- Assume the viewer has never heard of Hamsterdan.
- The story guide prepares the viewer, the GitHub card shows the event, and a
  later guide cue explains what changed.
- Henrique, Cris, and Dan are three collaborators in one plot. Avoid framing
  the story as “bot versus humans” or repeatedly labeling roles.
- Preserve provider truth where it matters: review findings attached to
  different lines are separate native review-thread cards.
- Explain consequence before internal mechanism. A digest is a confirmation
  lock tied to one requested mutation and one commit, not merely a long hash.
- The team retains merge authority. Readiness is a report, not an autonomous
  merge decision.

### Layout and motion

- Keep one compact, left-aligned message column. Do not offset collaborators
  left and right like a chat application.
- A new message appears beneath the current context and pushes older messages
  upward. Fade old context only after the act no longer needs it.
- The dashboard first appears directly beneath the PR as a normal GitHub
  message at the same width. It then makes a fast swoosh into the persistent
  right rail so viewers understand why that rail keeps changing.
- The dashboard is a semaphore: yellow means waiting or working, red means
  blocked, and green means ready.
- Use restrained motion: spring arrivals, a small card sway/pulse, and a brief
  dashboard pulse when status changes. Motion should direct attention, not
  compete with reading.
- Keep the title, act label, and story-guide band fixed. Reserve the content
  area below them; never allow explanatory copy to cover cards.

### Color and voice

- Henrique: blue. Cris: pink. Dan: orange.
- Dan may be precise and lightly characterful, but must not claim work has
  happened before provider evidence exists.
- Keep GitHub-like dark cards and file-location details. The style may evolve,
  but semantic colors and message hierarchy must remain clear.

## Cadence contract

Only the story-guide sentence and the main card text drive reading time.
Dashboard metadata, labels, hashes, file paths, and decorative chrome do not.

The default estimate is:

```text
hold_seconds = max(2.5, word_count / 3.8)
```

Then add approximately 0.8 seconds of transition margin. A guide cue should
settle about 1.2 seconds before its related card arrives. Longer review
findings, confirmation explanations, and final readiness copy should receive
additional judgment-based time.

`src/timing.ts` implements these defaults. Treat its result as the initial
schedule, then watch the full composition at normal speed. Avoid changing an
explanation cue and introducing a dense card at the same instant.

## Scenario worksheet

Before editing JSX, answer these in the new scenario file or a nearby note:

1. What changed in the pull request?
2. Who joins, and what evidence does each collaborator add?
3. Which GitHub events deserve their own cards?
4. Which event changes dashboard state, and only after what evidence?
5. Where does confirmation protect a branch mutation?
6. What blocks progress, and what resolves that exact blocker?
7. What is the final provider-observed state?
8. What should a first-time viewer understand after each act?

## QA checklist

Before accepting a candidate:

- [ ] TypeScript compiles with `bun run check`.
- [ ] Checkpoint stills cover every guide transition and message arrival.
- [ ] Guide copy settles before the related event.
- [ ] Main text remains readable before another card pushes it.
- [ ] Collaborators share one message column with compact vertical gaps.
- [ ] Review findings retain separate native review-thread shapes.
- [ ] Dashboard updates follow their causal event and use the right semaphore.
- [ ] No card clips, overlaps the guide, or disappears before it can be read.
- [ ] Act changes do not produce unintended blank frames.
- [ ] The final ready or terminal state has a comfortable hold.
- [ ] `ffprobe` reports one H.264 video stream and no audio stream.
- [ ] The complete encoded video—not only stills—has been watched once.

## Artifact policy

Commit this studio and scenario definitions. Do not commit routine MP4 renders
or checkpoint images. Publish approved videos as release assets so replacing a
candidate does not permanently inflate repository history.
