"""Minimum read-only permissions for pilot integrations."""

from __future__ import annotations

JIRA_REQUIRED_PERMISSIONS = [
    "Browse projects",
    "View issues",
    "View read-only workflow / transitions (for changelog where needed)",
]

JIRA_PERMISSIONS_NOTE = (
    "Requires read-only access: Browse Projects, View Issues, and workflow transition visibility. "
    "Classic tokens use the site URL; scoped service-account tokens use api.atlassian.com with a "
    "cloudId. Credentials are encrypted at rest and never displayed after saving."
)

ADO_REQUIRED_SCOPES = [
    "Code (Read)",
    "Build (Read)",
    "Release (Read)",
    "Project and Team (Read)",
]

ADO_PERMISSIONS_NOTE = (
    "Requires read-only PAT scopes: Code (Read), Build (Read), Release (Read), Project and Team (Read). "
    "Tokens are never echoed back after initial save."
)
