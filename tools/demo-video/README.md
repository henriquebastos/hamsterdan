# Hamsterdan demo-video studio

This directory has two independent media lanes:

- the Remotion studio turns a completed GitHub scenario into a guided,
  presentation-style product video; and
- the live-capture lane records assertion-checked screenshots of the real,
  public GitHub site and makes an unembellished checkpoint montage from only
  those screenshots.

The first lane preserves the approved PR47 hero journey and the production
rules needed to reproduce it or create another scenario without reconstructing
the creative brief from conversation history. The second supplies provider-
visible acceptance evidence; it is not a recreation and does not use Remotion.

The rendered MP4 is a generated release asset. Source, scenario copy, timing
rules, avatars, and render commands live here in Git.

## Capture real GitHub evidence

Checked-in manifests identify surviving checkpoints in the public GitHub UI.
`pr61-v5-hero.json` covers Cris's requested-changes review, three App findings,
Henrique's repair request, the App commit, the successful repaired-head Actions
run, operation-scoped recovery, status conversation, Cris's approval, and final
readiness. `pr56-v5-clean-green.json` covers exact-head green checks, the
successful Actions run, App dashboard, and readiness advisory.
`pr57-v5-transient-ci.json` covers the failed first Actions attempt, successful
rerun of that exact run and head, dashboard progression, and readiness.
`pr63-v6-hero.json` covers the closed production hero journey on PR #63: the
App's review findings, Henrique's change request, and the readiness advisory.
The browser context is anonymous, nonpersistent, and read only. It accepts no
login, cookie file, token, storage state, user profile, or arbitrary selector
from the manifest.

`expectedState` declares the pull-request state the capture must observe —
`open`, `closed`, or `merged`. The capture asserts the matching GitHub state
label and fails closed on any other state.

Run capture only from a clean committed worktree. The capture validates the
repository, PR state, exact head identity, actor identity, and checkpoint text
in the rendered DOM before atomically publishing any output:

```sh
cd tools/demo-video
bun install --frozen-lockfile
bunx playwright install --with-deps chromium
manifest=live/manifests/pr56-v5-clean-green.json
capture_dir="$(bun run --silent live/capture-cli.ts "$manifest")"
bun run live/render-cli.ts "$manifest" "$capture_dir"
```

The `capture:pr61`/`render:pr61` and `capture:pr63`/`render:pr63` package
scripts remain shortcuts for the complete hero manifests.

The output is written under:

```text
output/live/<manifest-slug>/<utc>-<manifest-digest>/
  dom/<checkpoint>.before.html
  dom/<checkpoint>.after.html
  checkpoints/<checkpoint>.png
  report.json
  hamsterdan-<manifest-slug>-live-checkpoints.mp4
  SHA256SUMS
```

Each checkpoint produces the three layers the 2026-09-02 evidence ruling
requires, in that order of authority:

1. The rendered DOM saved as HTML on both sides of the action the checkpoint
   performs on the page — `before` immediately after the checkpoint document is
   ready, `after` once the checkpoint's focus scroll has run.
   Both capture and watch use SingleFile Core to embed stylesheets, nested
   images and fonts, and rendered shadow DOM. The complete document retains
   its root attributes; automatic color-scheme rules are frozen to the capture
   environment. Scripts and frames are removed. Missing required resources
   fail the capture. The anonymous request boundary still applies to resource
   fetches. Opening the saved HTML requires no network access.
2. A full-page PNG whose pixel height is verified mechanically against the
   page's own real height,
   `max(document.body.scrollHeight, document.documentElement.scrollHeight)`, at
   capture time. The body number alone runs short whenever a trailing margin
   escapes the body box. A mismatch is retried up to three times and then fails
   the whole capture; a cropped still is never published. A page shorter than
   the viewport is exactly one viewport tall. No PDF is written anywhere.
3. The video: either the literal montage MP4 or the transition render, both
   assembled after the run from those stills.

Each checkpoint also records `anchor`, the document-coordinate bounding box of
its target element. Pixels alone cannot say which comment a still is about, and
the transition renderer needs that box to frame a static journey.

The report records bounded provenance, assertion hashes, final URLs, browser
version, still hashes and dimensions, the observed `scrollHeight` and attempt
count, the target's anchor box, the DOM file hashes and byte lengths, and
`ffprobe` video metadata. It
embeds no page HTML, headers, cookies, HAR files, traces, arbitrary page text,
or credentials — the DOM lives only in `dom/`, hash-bound by the report. The
renderer rejects missing, changed, reordered, or unreported PNGs and DOM files,
rejects any still whose pixels no longer match its recorded height, and adds no
cards, captions, overlays, interpolation, or simulated browser chrome. Because
full-page stills are taller than the montage canvas, each still is fitted whole
into the frame and letterboxed; it is never cropped back to the viewport. A
1280×4653 page fitted into 1280×720 is an unreadable sliver, so the montage is
an integrity artifact, not the deliverable a viewer watches. For that, render
transitions.

## Watch a live journey

`bun run watch <manifest> [--poll-seconds=N] [--duration-seconds=N]` reloads the
pull-request page on a cadence and records one numbered state — before and after
DOM plus a height-verified full-page PNG — every time the page's visible content
actually changes. The cadence, total duration, state ceiling, and caption come
from the manifest's optional `watch` block; the two CLI flags override cadence
and duration. States are numbered `state-001` upward and carry their own
timestamps, so the capture is the complete ordered sequence of page states.

The browser context, allowed hosts, read-only routing, and fail-closed checks
are the ones the checkpoint lane uses. Every poll re-asserts the repository, the
declared pull-request state, and at least one declared actor; a challenge page,
a login redirect, or a state change fails the whole run without publishing. A
run that never saw two distinct states fails rather than publishing a video of
one frame repeated. Output goes to `output/live/<slug>-states/<utc>-<digest>/`.

## Render readable transitions

```sh
bun run transitions <manifest> <capture directory>          # checkpoint capture
bun run transitions <manifest> <capture directory> --states # watched sequence
```

The transition renderer shows, at 1:1, the part of the page that changed:

- it diffs each consecutive pair of stills by row and column and takes the
  bounding box of the changed pixels;
- when that box fits the 1280×664 evidence pane, the video holds state N for
  one guide lead, crossfades for one transition margin, then holds state N+1
  for its caption's reading time — all cropped from the real stills;
- when the two stills are pixel-identical, or the change is smeared across the
  whole page (a closed pull request redraws every relative timestamp), it
  frames the arriving checkpoint's recorded `anchor` instead;
- when the capture recorded no anchor, it walks the camera evenly down the
  page, one window per state.

Pacing comes from `src/timing.ts` — the same words-per-second and minimum-hold
rules the Remotion lane uses — rounded to whole frames so the encoded duration
equals the planned duration. Every caption is manifest text: a checkpoint
transition uses the arriving checkpoint's asserted `focusText`, and a watched
transition uses `watch.caption` with the state number.

The only authored pixels are a 1280×56 caption strip below the evidence pane.
Nothing is scaled, so text stays exactly as the browser rendered it.

Output is a sibling directory that never rewrites the capture:

```text
<capture directory>/transitions/
  hamsterdan-<manifest-slug>-<live|fixture>-transitions.mp4
  transitions.json
  SHA256SUMS
```

`transitions.json` binds the render to the capture by manifest hash and report
hash, and records every transition's framing decision, crop window, changed
pixel count, pacing, and caption alongside the `ffprobe` video metadata.

This deliverable is a **checkpoint montage captured later from surviving public
evidence**, not contemporaneous footage of the original interactions. Inspect
every PNG and watch the complete MP4 once before approval. Routine output stays
ignored; publish an approved MP4, checkpoint archive, report, and checksum file
together as immutable versioned release assets or in durable media storage.

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

PR83's older HTML omitted root attributes and referenced remote assets. Repair
those saved documents with the command below, writing to a separate directory:

```bash
bun run live/recover-html-cli.ts \
  output/proof/cv19-pr83/40-all-clear.before.html \
  output/proof/html-recovery-20260905/pr83/40-all-clear.before.html \
  dark https://github.com/HBNetwork/demo-pr-readiness/pull/83
```

Use `light` for PR83 checkpoints 03–17 and `dark` for checkpoints 22–50, as
observed in their PNGs. Recovery restores known GitHub root attributes, blocks
the original scripts, embeds newly fetched public assets, and reopens the
result in a fresh offline browser. Adjacent `.html.json` and `.html.png` files
record the source/output hashes, image and network checks, and whether the
restored online and offline screenshots match. Existing outputs are never
overwritten. These are later derivatives: uncaptured relative timestamps and
other transient browser state remain unavailable. Preserve the original proof
archive and use its accepted PNGs for contemporaneous visual claims.

Commit this studio and scenario definitions. Do not commit routine MP4 renders
or checkpoint images. Publish approved videos as release assets so replacing a
candidate does not permanently inflate repository history.
