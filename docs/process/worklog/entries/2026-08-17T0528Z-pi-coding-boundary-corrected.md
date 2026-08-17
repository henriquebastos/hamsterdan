# Pi coding boundary corrected locally

After the selected-V5 hero finding checkpoint, the author made one explicit
repair request on
[`HBNetwork/demo-pr-readiness` PR 59](https://github.com/HBNetwork/demo-pr-readiness/pull/59#issuecomment-5311803608).
The globally identified Pi coding operation exhausted its 16 admitted calls
before a write and settled as typed `DeclinedM(category="unable")` at unchanged
head `493a99512a92aa0a21c02880319d7a2d32d1816f`. PR 59 remains retained
fail-closed evidence and was not retried.

Hamsterdan now pins Petrus correction
[`9bc68d8`](https://github.com/henriquebastos/petrus/commit/9bc68d8a5cddb7111c8e5dceae8251c9401df11a),
which advertises only the operation's exact current grant and raises the
version-1 whole-file write ceiling to 1,024 characters. Only coding operations
receive a 32-call policy; review and conversation operations remain
read/search-only at 16 calls. Global host capabilities, credentials, archive
proof, patch admission, current-authority fences, host-owned exact ref CAS, and
typed inability settlement are unchanged.

Ninety focused workspace/runtime/mutation tests, quick checks, 1,171 Python
tests, and nine Bun relay tests passed. A fresh selected-V5 hero PR remains
required to qualify real Git publication, CAS admission, and the visible repair
journey under the corrected boundary.
