---
status: Resolved
raised: 2026-09-05
resolved: 2026-09-05
related:
  - ../../roadmap/cv19-private-v0-1-production/proof/pr80.md
  - ../../roadmap/cv19-private-v0-1-production/proof/pr83.md
---

# 1. HTML proof captures omit assets and root attributes

The Navigator reported that saved proof HTML does not reproduce GitHub's
appearance and is not self-contained. Inspection confirmed both defects in
all 12 PR80 HTML files and all 21 PR83 HTML files.

The local capture helpers used `agent-browser get html html`, which serializes
the contents of the document element rather than its outer markup. The files
start with a doctype followed by `<head>` and omit `<html>` and its attributes,
including `data-color-mode`, `data-light-theme`, and `data-dark-theme`.
They also retain external stylesheet, image, and script references without
packaging the referenced resources. PR83's final HTML contains 49 remote
stylesheet links. The maintained capture/watch lane uses `page.content()`,
which preserves the root, but likewise does not bundle external resources.

An anonymous browser opened `40-all-clear.before.html` with networking disabled.
The body used the Times fallback font, its background was transparent, and all
19 image elements failed to load. Enabling networking restored the expected
font and images but left the background transparent. Restoring only the missing
theme attributes in the diagnostic browser changed the background to the live
dark theme's `rgb(13, 17, 23)`. The original files were not edited.

These files preserve serialized DOM evidence, not self-contained visual pages.
The accepted PNGs remain the contemporaneous visual records. Original HTML and
archive hashes must remain immutable; any recovered view must be labeled as a
later derivative. Historical root attributes and uncaptured resource bytes
cannot be claimed as retained evidence merely by fetching today's page.

The correction should capture the complete rendered document and its theme,
bundle CSS and nested font/image dependencies, preserve rendered custom-element
content, and prevent runtime scripts from changing the archived view. Validate
the result in a fresh browser with networking blocked, checking failed resource
loads and comparing its rendered image with the captured PNG. An inline-only
fixture cannot test the missing-resource failure. This investigation establishes
the defect.

## 1a. Resolution

Commit `1225895` adds SingleFile Core resource packaging to both maintained
capture paths. The full document, assets and rendered shadow DOM are archived;
scripts are removed and automatic color-scheme conditions are frozen. Missing
resources fail capture. Browser tests cover external CSS with nested imports,
images and fonts, shadow content, unchanged live-page pixels, offline rendering
under the opposite theme preference, and missing-resource rejection. All 112
media checks pass, with no skips.

The Navigator limited historical repair to PR83. Its 21 recovered HTML files
and verification results are recorded in the
[recovery manifest](../../roadmap/cv19-private-v0-1-production/proof/pr83-html-recovery-manifest.json).
They restore observed GitHub root attributes and fetch public assets at recovery
time. Original proof files and hashes remain unchanged. Absolute timestamps
remain where the original serialization omitted rendered relative-time shadow
content; this historical loss is explicit, not a claim of exact restoration.
PR80 recovery is outside the accepted scope.
