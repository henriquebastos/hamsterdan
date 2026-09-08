# 1. Contributing

Hamsterdan is an early source publication. Issues may describe bugs, ask
questions, or propose changes. Discuss substantial changes before opening a
pull request. Maintainer review and response times are not guaranteed.

The pinned Petrus source dependency is public. Public CI remains disabled, and
the existing build wrappers still use a build-vault credential. Running the
application requires GitHub App and AI credentials; never submit credentials
in a contribution.

Follow the
[development guide](docs/process/development-guide.md). Use Python 3.14, uv,
Bun 1.3.10, and Bash 5. Run `scripts/check full` and include the result and any
checks you could not run in the pull request. Keep changes focused and add
tests for changed behavior.

`src/hamsterdan` is the current V5 runtime. `src/hamsterdan2` is unfinished,
non-selectable replacement work. Exploration records and the optional demo
studio preserve historical work; they are not supported application entry
points. Test helpers and internal modules have no stable public API contract.
Historical version tags describe private qualification, not public releases.

Keep secrets, raw webhook payloads, private source, and local runtime state out
of commits. Use the [security reporting route](SECURITY.md) for vulnerabilities.
Participation follows the [code of conduct](CODE_OF_CONDUCT.md).

Hamsterdan contributions use the [Apache License 2.0](LICENSE). Preserve
existing third-party license and attribution notices.
