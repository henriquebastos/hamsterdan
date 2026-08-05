# Pi A2 workspace archives lack safe host-tree application

**Status:** Resolved locally at Petrus `750c4321bb51563666ce43e88f753ebe1f068520`

**Raised:** 2026-08-05

**Related:** CV16.DS11

Petrus publishes a bounded, digest-verified opaque workspace archive only after
aggregate cleanup. It restores that archive for native continuation, but does
not apply or merge it into a receiving host tree. Hamsterdan's unchanged coding
contract publishes a strictly correlated binary patch against the current PR
head. Trusting model-emitted patch text independently of the settled workspace,
or extracting over a live checkout, would create an unfenced split source of
truth.

Petrus schema-2 now binds a canonical per-start archive, digest, route
correlation, and effective attachment policy into replay identity. Hamsterdan
exports the exact requested head, privately validates and extracts the settled
archive, derives an indexed binary patch, and reproduces its result tree before
returning the unchanged coding contract. Current-authority reads, patch
application, operation recovery, and exact ref CAS remain in `HostGitPublisher`.

The receiver deliberately refuses links, submodules, special files, unsafe or
control paths, unsupported modes, empty directories, and bounded-size excess.
Its Git fetch has a time limit but no transfer-byte quota before tracked-tree
admission, so admitted repository size remains an accepted host resource limit.
