# Security review (pilot)

Review date: 2026-07-31. Scope: credentials, browser exposure, SSRF, prompt injection, remote participation, uploads, authz, XSS/CSRF, rate limits, logging, reports.

## Confirmed controls

| Area | Control |
| --- | --- |
| Jira / ADO secrets | Fernet encryption at rest; API returns `*_configured` booleans only |
| Encryption keys | Required outside development/test; never returned by APIs |
| Browser exposure | No `VITE_*` vendor secrets; OpenAI key server-side; voice uses ephemeral client secret |
| SSRF | HTTPS-only; reject userinfo; reject private/link-local IP literals; allowlist Atlassian / Azure DevOps hosts |
| Prompt injection | `sanitize_remote_text`; interview + scoring instructions treat content as untrusted; structured outputs |
| Remote contributions | Signed timed invites, revocation, assessment binding, rate limits, untrusted trust marker |
| Uploads | MIME/ext allowlist, size cap, magic sniff, sanitized names under `uploads/remote/` |
| Admin auth | bcrypt password, HttpOnly SameSite cookie, CSRF Origin + `Sec-Fetch-Site` checks |
| Login abuse | Admin login rate limit (5 / 5 minutes / client key) |
| Mock host auth | Explicit `ALLOW_MOCK_HOST_AUTH` (local/test only); forbidden in staging/production |
| Coverage secrecy | Participant coverage omits AI scores; requires host/admin auth |
| XSS | React text rendering; no `dangerouslySetInnerHTML` |
| Logging | Redacting filter + audit key redaction |
| Publication | AI candidate scores stripped from public results; immutable published versions |

## Intentional pilot tradeoffs

| Topic | Decision |
| --- | --- |
| Published results by UUID | Capability URL for pilot sharing; treat UUID as secret-ish |
| Invite token in query string | Convenient for Figma join links; prefer fragment exchange later |
| In-memory rate limiter | Acceptable with one Uvicorn worker / one replica |
| Custom JQL | Admin-controlled; service account must stay read-only scoped |

## Fixes applied in this pass

- Participant coverage requires host/admin auth
- Integration URL host allowlist + private IP rejection
- Admin login rate limiting
- `ALLOW_MOCK_HOST_AUTH` explicit opt-in
- CSRF rejects `Sec-Fetch-Site: cross-site`
- Live scoring prompt hardened for untrusted content
- Export path resolution uses `Path.relative_to`

## Residual known limitations

- DNS-rebinding SSRF not fully pinned (hostname allowlist only)
- `sanitize_remote_text` is defense-in-depth, not complete NLP safety
- No enterprise SSO / MFA
- Weak Content-Security-Policy beyond `frame-ancestors`
- Key rotation for `DATA_ENCRYPTION_KEY` is operational (re-encrypt not automated)
