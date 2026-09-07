# 1. Secrets cutover and PR84 comparison passed

Production now runs release `85c109e` through the shared 1Password Environment
loader. VM qualification, provisioning, idempotent reapplication, actual App
validation and a supervised restart passed. The old active credential files
were removed after their bytes matched protected recovery. All 20 existing PR
histories remain intact. Isolated deployed-image probes refused startup for
denied access, missing bootstrap and missing required AI key, and authenticated
OpenAI access passed with the loader token excluded from the application child.

[PR84](../../../project/roadmap/cv19-private-v0-1-production/proof/pr84.md)
passed the same full hero journey as PR83. Both opening and repaired source
trees match the baseline exactly. The App found and repaired the same three
defects, both heads passed six CI jobs, and a clear rereview resolved all three
App threads before Cris approved. One readiness advisory followed and the
original summary became all-clear. Strict opening and final inspectors each
passed all ten checks. The test PR was closed unmerged; PR83 was untouched.

The 2,390-record preclosure and 2,461-record post-closure histories replayed
without effects and contain no failed or pending Activities. Production remains
healthy with zero scheduler errors and `NRestarts=0`. Timing, prose, summary
publication count and ordinary webhook deferral counts vary from PR83; the
observed functional results match. Screenshot freshness limits are explicit in
the linked proof and manifest.

[RS-037](../../../project/workbench/rs-037-single-authority-secrets.md) remains
Active for remote Amp settings and fresh-orb qualification.
The 1Password web session requires a fresh sign-in to create Amp-specific
readers. No issuer credentials were rotated, recovery deleted, or runtime code
changed during the production comparison. The Navigator accepted the result
and authorized committing and pushing this operational receipt and related
documentation.
