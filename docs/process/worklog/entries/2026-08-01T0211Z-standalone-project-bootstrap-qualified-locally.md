# Standalone project bootstrap qualified locally

**Time:** 2026-08-01T02:11:03Z
**Roadmap:** CV1.DS1

Hamsterdan became an independently installable application project with its own
Ariad memory, `src/` package, dependency lock, test/check route, CI definition,
and orb setup contract. The project pins Petrus to
`cd1187e44926d6a80e4a3538ad79762618d32a8b`, the accepted ownership and
namespace-migration commit.

Executable architecture tests establish the approved boundary: `host` alone
may compose concrete `github_app`, `agents`, and `readiness` siblings, while the
siblings may share only neutral contracts. An isolated wheel installation
resolved Petrus from the exact VCS revision and imported `Engine`, `NetSpec`,
`Net`, and `ActivityDefinition` from their defining modules.

Local qualification passed four tests, Ruff lint and format checks, ty source
analysis, wheel/sdist build and content inspection, frozen setup, and resume.
No GitHub App authentication, webhook ingress, provider effect, agent adapter,
or transferred PR-readiness implementation was added in this bootstrap.

The personal Amp project exists at `@henriquebastos/hamsterdan`. Creating the
empty private `henriquebastos/hamsterdan` GitHub repository is pending because
the current automation credential cannot create repositories; source history
therefore remains local and uncommitted until the Navigator accepts the
checkpoint and supplies that provider prerequisite.
