# Development secret template — direnv renders it to the gitignored `.env` and
# loads that file into the shell. Non-secret runtime configuration (file paths,
# App ids, logins) belongs in the deployment environment, not here.
AI_MEMORY_AUTH_TOKEN="op://hamsterdan-dev/ai-memory-auth-token/credential"
AMP_API_KEY="op://hamsterdan-dev/amp-api-key/credential"
CF_ACCESS_CLIENT_ID="op://hamsterdan-dev/cf-access-clients/client_id"
CF_ACCESS_CLIENT_SECRET="op://hamsterdan-dev/cf-access-clients/client_secret"
E2B_API_KEY="op://hamsterdan-dev/e2b/credential"
GITHUB_HENRIQUEBASTOS_HOSTS="op://hamsterdan-dev/github-henriquebastos-hosts/credential"
HAMSTERDAN_GITHUB_WORKFLOW_TOKEN="op://hamsterdan-dev/github-workflow-token/credential"
OPENAI_AGENT_API_KEY="op://hamsterdan-dev/openai/credential"
OPENAI_API_KEY="op://hamsterdan-dev/openai/credential"
OPENROUTER_API_KEY="op://hamsterdan-dev/openrouter/credential"
PETRUS_GITHUB_TOKEN="op://hamsterdan-dev/petrus-github-token/credential"
