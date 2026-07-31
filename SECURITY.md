# Security Policy

## Reporting a vulnerability

If you discover a security issue in SAFe2DevOps, report it privately to the repository owner (`carlosevp`). Do not open a public issue that includes secrets, tokens, or exploit details.

## Hard rules for this project

- Never commit `.env`, PATs, API tokens, service-account keys, or session secrets
- Never log full credentials, Authorization headers, or raw OpenAI API keys
- Store Jira and Azure DevOps credentials server-side only; mask them in the UI after save
- Prefer least-privilege, read-only scopes for Jira and Azure DevOps integrations
- Do not expose internal SQLite paths, admin-only APIs, or unpublished assessment content without auth
- Treat assessment transcripts and remote contributions as sensitive organizational data

## Credential placeholders in the Figma UI

The Figma frontend may show masked placeholder credential strings for design fidelity. Those values are mock UI data, not production secrets. Real credentials belong only in environment variables or a secrets manager.

## Deployment notes

- Railway (test) and OpenShift (final) must inject secrets via platform secret mechanisms
- SQLite files live on mounted persistent storage and must not be committed
- Run exactly one application replica while SQLite is the persistence layer
