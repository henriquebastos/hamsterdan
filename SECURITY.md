# 1. Security reports

Report suspected vulnerabilities privately to henrique@bastos.net. Include the
affected revision, a minimal reproduction, and the expected impact. Remove
credentials, private repository contents, and webhook payloads from your report.
Do not put exploitable details or credentials in a public issue or pull request.

This repository is an early source publication. There is no supported release
series, guaranteed response time, or bug bounty. Security fixes will be tracked
on `main`; historical tags are not maintained security branches.

Host startup and operator commands can act on GitHub repositories. Follow the
[operator documentation](docs/operator/README.md) and use an isolated App,
repository, and state directory when investigating a report.
