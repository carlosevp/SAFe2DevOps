"""Minimum read-only permissions for pilot integrations."""

from __future__ import annotations

JIRA_REQUIRED_PERMISSIONS = [
    "Browse projects",
    "View issues",
    "View read-only workflow / transitions (for changelog where needed)",
]

JIRA_PERMISSIONS_NOTE = (
    "Requires read-only access: browse projects, view issues, and view workflow transitions. "
    "Service account credentials are encrypted at rest and never displayed in full after saving."
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
