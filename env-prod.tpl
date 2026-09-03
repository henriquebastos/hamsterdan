# Production runtime environment contract. Provisioning copies this file to
# /etc/hamsterdan/env-prod.tpl; the systemd unit resolves it into
# /etc/hamsterdan/hamsterdan.env at every service start. It carries runtime
# configuration and secret file paths, never secret values.
HAMSTERDAN_GITHUB_APP_ID={{ op://hamsterdan-prod/github-app/app_id }}
HAMSTERDAN_GITHUB_APP_SLUG={{ op://hamsterdan-prod/github-app/slug }}
HAMSTERDAN_GITHUB_CLIENT_ID={{ op://hamsterdan-prod/github-app/client_id }}
HAMSTERDAN_GITHUB_INSTALLATIONS_FILE=/run/config/hamsterdan/installations.toml
HAMSTERDAN_STATE_PATH=/var/lib/hamsterdan
HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE=/run/secrets/hamsterdan/github-app.pem
HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE=/run/secrets/hamsterdan/webhook-secret
HAMSTERDAN_PI_PROVIDER=anthropic
HAMSTERDAN_PI_MODEL=claude-sonnet-4-5
HAMSTERDAN_PI_API_KEY_FILE=/run/secrets/hamsterdan/agent-api-key
HAMSTERDAN_WORKFLOW_PATH=.github/workflows/ci.yml
HAMSTERDAN_REMINDER_SECONDS=259200
