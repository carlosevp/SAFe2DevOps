# Known limitations

## SQLite

- Exactly one application replica and one Uvicorn worker
- No horizontal autoscaling
- Default journal mode `DELETE` (portable); WAL only on validated local disk
- Short transactions; busy timeout configurable

## Product / UX

- Client-side screen state (no React Router / deep-link persistence for assessment id)
- Workshop side panels hidden below `lg`
- Setup wizard invite copy UI is illustrative; real invites are created in the workshop
- Admin review Evidence / Transcript nav sections are thin placeholders
- Some AI settings toggles are local UI-only
- Enterprise Standards Overlay enriches interview/recommendations but does not change SAFe maturity scores, produce a numeric enterprise-alignment score, or block publication

## Security / sharing

- Published results are reachable by assessment UUID (capability URL)
- Remote invite tokens appear in query strings
- No enterprise SSO / MFA
- DNS-rebinding resistant SSRF pinning is not fully implemented

## Integrations

- Live Jira/ADO require read-only scoped credentials (see integrations-permissions.md)
- Custom JQL is admin-controlled; mis-scoped service accounts can over-collect

## Operations

- In-memory rate limiter (single process)
- Encryption key rotation is manual
- OpenShift deploy from CI is manual and gated
