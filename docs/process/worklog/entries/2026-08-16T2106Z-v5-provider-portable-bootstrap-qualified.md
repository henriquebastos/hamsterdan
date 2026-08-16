# V5 provider-portable bootstrap qualified locally

The CV17 live bootstrap no longer requires Anthropic specifically. Fresh setup
selects exactly one qualified direct Pi route in explicit Anthropic, OpenAI,
OpenRouter order, retains one generic private authority file, and emits exact
provider/model metadata through the checked launcher. Pi installation metadata
is parsed once; the same selection owns Agenticus route identity and Petrus
runtime composition. Existing Pi state cannot be silently rebound to another
provider: an atomically published, fsynced, private nonsecret marker rejects a
changed pair before key consumption or runtime construction. Tests cover
competing provider writers, a post-publication crash cut, restrictive umask,
unsafe key custody, exact launcher admission, stale authority retirement, and
all three qualified choices.

The recovered GitHub App key and webhook secret and the available OpenAI key
are now project secrets alongside the author and reviewer role sessions. This
lets future Hamsterdan project orbs reproduce provider setup without copying
authority from a historical thread. Public App inventory still lacks the
required `pull_request_review_thread` event, so no live collaboration claim or
fresh PR was attempted in this slice.

Final verification passed 1,121 Python tests and nine Bun relay tests plus
Ruff, formatting, typing, and source/wheel builds. Oracle review returned
`clear to commit` after atomic publication, explicit route identity, and
restrictive-umask findings were closed.
