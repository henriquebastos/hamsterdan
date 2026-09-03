---
status: Decided
raised: 2026-09-02
decided: 2026-09-02
recorded: 2026-09-02T1940Z
deciders:
  - Henrique (Navigator)
related:
  - CV19
  - ../../roadmap/cv19-private-v0-1-production/index.md
  - ../../../process/worklog/entries/2026-09-02T0235Z-gate-b-patch-releases-and-hero-journey-in-production.md
---

# Evidence captures are full-page and full-screen

## Decision

Web-page evidence for hero journeys and demos is captured in three layers at
every checkpoint, in this order of authority:

1. **Page state (authoritative):** the rendered DOM saved as HTML, captured
   both **before and after** each checkpoint, plus the underlying data — the
   GitHub API objects and the History records (board versions live in
   `DashLanded` entries). State can be re-rendered, re-screenshotted at any
   size, and analyzed later; pixels cannot.
2. **Stills:** a full-page PNG of the same page. Every full-page PNG is
   verified mechanically: its pixel height must equal the page's real height,
   `max(document.body.scrollHeight, document.documentElement.scrollHeight)`
   (the body number alone runs short when a trailing margin escapes the body
   box) — a capture that fails the check is redone, not kept. PDFs are not part of the package (Navigator ruling,
   2026-09-02): images and video only.
3. **Video:** used only to show motion and live updates in a narrative.
   It may be assembled after the run from the checkpoint DOM/still
   captures instead of recorded live, provided layer 1 and 2 exist for
   every checkpoint. Video is never the evidence of record, because a
   frame can only ever show the viewport of a page that grows vertically.

Viewport-only shots are allowed only when the visible area itself is the
subject, such as an above-the-fold layout check.

## Rationale

The 2026-09-01 hero-journey screenshots for PR #63 were cropped because the
PR pages were longer than the viewport, and the recordings show only the
browser client area. Cropped captures lose the content below the fold — the
findings comments and decision boards the evidence exists to preserve — so
they cannot back the narrative Henrique needs to explain and prove
Hamsterdan to other people.

## Consequences

- The existing PR #63 stills and clips are demoted to partial evidence; the
  proof package CV19 now requires must be captured under this ruling. The
  final state of the PR #63 page was recaptured under it on 2026-09-02
  (`page-final/` in the archive: verified full-page PNG and DOM HTML; the PDF
  captured alongside them predates the images-and-video-only refinement and
  stays in the archive as historical material only).
- Intermediate board states are edited in place on GitHub, so their visual
  record exists only if captured at checkpoint time — but their content is
  always reconstructable from History's `DashLanded` entries, which the
  CV19 evidence exporter must surface.
- Recording sessions pair full-screen video with the layer-1 and layer-2
  captures at each checkpoint; video alone proves nothing about page
  content.
