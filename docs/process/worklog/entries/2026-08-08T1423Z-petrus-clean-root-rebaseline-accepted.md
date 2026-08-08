# Petrus clean-root re-baseline accepted technically

Hamsterdan now pins the public Petrus dependency exactly to
`116b0ddc460c0e04d4ad40c077158bd3498a4860` over HTTPS. This is a technical
clean-root re-baseline, not an ancestral upgrade from the historical
`750c4321bb51563666ce43e88f753ebe1f068520` qualification revision. The
Navigator's prior approval of the Petrus clean-history plan accepts that
history boundary; completed worklogs, resolved debt, and roadmap evidence keep
the revisions that were actually qualified.

The regenerated Python 3.14 lock contains the exact HTTPS revision and resolved
fragment. A frozen sync fetched the public dependency without a deploy key or
SSH setup. Ruff, formatting, and ty passed; all nine Bun tests passed; wheel and
source distributions built and contained the exact Petrus direct reference;
and the full Python suite passed 369 tests with zero skips while deselecting the
one explicit opt-in real Amp provider acceptance test. A focused CI assertion
confirmed that the workflow retains the frozen sync and full check while
containing no Petrus deploy-key, SSH command, keyscan, key-file, or known-host
coupling.

This acceptance covers dependency resolution, package compatibility, tests,
static checks, and distribution metadata. It does not claim a production host
restart, production-state inspection, provider invocation, or mutation.
