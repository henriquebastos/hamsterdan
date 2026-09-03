# Secret template — resolve with: op run --env-file env.tpl -- <command>
# Requires OP_SERVICE_ACCOUNT_TOKEN (sa-hamsterdan). Non-secret runtime config
# (file paths, app ids, logins) belongs in the deployment env, not here.
AI_MEMORY_AUTH_TOKEN="op://global/ai-memory-auth-token/credential"
AMP_API_KEY="op://hamsterdan/amp-api-key-hamsterdan/credential"
CF_ACCESS_CLIENT_ID="op://global/cf-access-clients/client_id"
CF_ACCESS_CLIENT_SECRET="op://global/cf-access-clients/client_secret"
E2B_API_KEY="op://global/e2b-shared/credential"
EXE_DEV_API_TOKEN="op://hamsterdan/exe-dev-hamsterdan/credential"
GITHUB_HENRIQUEBASTOS_HOSTS="op://global/github-henriquebastos-hosts/credential"
HAMSTERDAN_GITHUB_WORKFLOW_TOKEN="op://hamsterdan/hamsterdan-github-workflow-token/credential"
OPENAI_AGENT_API_KEY="op://global/openai-shared/credential"
OPENAI_API_KEY="op://global/openai-shared/credential"
OPENROUTER_API_KEY="op://global/openrouter-shared/credential"
PETRUS_GITHUB_TOKEN="op://hamsterdan/petrus-github-token/credential"
