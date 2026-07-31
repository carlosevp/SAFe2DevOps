# Integration permissions (pilot)

## Jira Cloud (read-only)

Minimum access for the service account:

- Browse projects
- View issues
- View workflow / transitions (changelog where needed)

Do **not** grant create/edit/delete issue permissions for the pilot.

Credentials:

- Site URL (`https://…atlassian.net`)
- Service account email
- API token

Tokens are encrypted at rest and never returned by API schemas after save.

## Azure DevOps Services (read-only)

Minimum PAT scopes:

- Code (Read)
- Build (Read)
- Release (Read)
- Project and Team (Read)

Organization URL must be HTTPS (`https://dev.azure.com/<org>`).

## Provider modes

- `INTEGRATION_PROVIDER=mock` (default locally/tests): deterministic mock adapters
- `INTEGRATION_PROVIDER=live`: real Jira/ADO HTTP adapters with timeouts and bounded retries
