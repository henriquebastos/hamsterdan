# Checkpoint

A named point the server durably records it reached while handling one pull request, such as "recorded in the webhook inbox". After a crash, work resumes from the last checkpoint instead of starting over or double-acting.

Avoid: cut

Related: [Webhook Inbox](webhook-inbox.md), [Stage](stage.md)
