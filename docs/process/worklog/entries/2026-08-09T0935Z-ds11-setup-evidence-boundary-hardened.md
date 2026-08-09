# DS11 setup evidence boundary hardened

The credential-free follow-up to the stopped CV16.DS11 setup now provides one
reusable closed boundary for private target observations and the exact atomic
two-ref push. Observation, timeout, fence, runner, and arbitrary ordinary
exceptions retain only fixed categories and booleans; command arguments,
coordinates, stdout, stderr, and exception prose cannot enter returned evidence.
Strict observation admission rejects false and non-boolean claims.

Push admission accepts only an exact canonical GitHub HTTPS remote and two
distinct lowercase SHA-1 object IDs, then generates only the declared non-forced
atomic base/head refspecs. A held no-follow private directory descriptor creates
the spent marker exclusively, forces and verifies mode `0600`, verifies marker
entry identity, syncs the file and directory, and rechecks the selected parent
before the runner can execute. Existing, malformed, symlinked, partially written,
unsynced, or path-substituted fences cannot run. Once admitted, every outcome is
terminal and every later invocation is refused.

Independent review found and closed parent-path TOCTOU, restrictive-umask,
URL-normalization, hostile string-subclass, and fence-close exception gaps. Fifty
focused qualification tests pass. The full project gate passes formatting, Ruff,
ty, nine Bun tests, source and wheel builds, and 397 Python tests with one provider
test deselected. No secret, GitHub, target, cleanup, direct-key, provider, remote,
or DS12 operation occurred. The rendering implementation gap is resolved;
separate exact-target cleanup obligations and the live qualification gate remain
open and authorize nothing.
