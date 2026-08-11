# Git object protocol given one provider owner

Hamsterdan moved GitHub blob, tree, and commit wire construction and exact
response proof into `GitHubAuthority`. Host publication still admits the patch,
proves the expected tree before commit creation, checks current PR authority,
and authorizes the exact ref compare-and-swap.

Focused evidence passed 86 tests. Quick and full static/type/format/package and
relay gates passed; the Python suite passed 597 tests with one external route
deselected. Adversarial review caught and corrected a weakened expected-tree
gate in the first extraction; final review approved the two-phase provider API
with no release blocker.
