# Deployment authority template. `scripts/ops` resolves it with `op run` for the
# duration of one command: personal 1Password authentication on a workstation,
# the sa-hamsterdan-ops-amp service account in a headless environment. It is
# never rendered to a file and never installed on a target.
OPENAI_AGENT_API_KEY=op://hamsterdan-ops/openai/credential
EXE_DEV_API_TOKEN=op://example-ops/example-api-token/credential
EXE_DEV_SSH_PRIVATE_KEY_B64=op://example-ops/example-ssh-key/credential
GITHUB_APP_ID=op://hamsterdan-ops/github-app-identity/app_id
GITHUB_APP_SLUG=op://hamsterdan-ops/github-app-identity/slug
OP_SERVICE_ACCOUNT_TOKEN_VPS=op://hamsterdan-ops/sa-hamsterdan-prod-exe/credential
