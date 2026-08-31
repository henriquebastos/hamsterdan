# Webhook Inbox

The database table where every incoming GitHub webhook is saved before anything else happens. The HTTP handler verifies the signature, writes the row, and answers 200; a worker processes rows later, dropping duplicates by delivery id.

Avoid: custody (for this), webhook custody, delivery custody

Related: [PR Identity](pr-identity.md)
