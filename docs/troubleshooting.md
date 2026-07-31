# Troubleshooting

## App will not become ready

1. Check `DATA_DIR` is writable (`./data` locally, `/data` in containers).
2. Confirm Alembic migrations succeed (`python -m app.core.bootstrap`).
3. Inspect `/api/health/ready` JSON for storage/db checks.
4. Ensure SQLite path stays under `$DATA_DIR/db`.

## Admin APIs return 401 in local mock mode

Set `ALLOW_MOCK_HOST_AUTH=true` for Figma-style host wiring **or** log in with the demo password from `data/.demo-admin-password`.

Never enable mock-host auth in staging/production (bootstrap refuses).

## Integrations test fails

- Mock mode needs no real tokens.
- Live mode requires HTTPS Atlassian / Azure DevOps hosts (private IPs and arbitrary hosts are rejected).
- Confirm encrypted secrets were saved (`*_configured: true`).

## Voice microphone fails

- Browser must allow microphone on the same origin.
- `OPENAI_API_KEY` required for live Realtime minting.
- Mock interview mode can still type answers without voice.

## Remote invite invalid

- Link must include `?invite=` token from workshop invite creation.
- Expired / revoked invites fail closed.
- Welcome “Join” without a token is expected to error.

## Workshop panels missing on a laptop

Coverage and contribution inbox hide below the `lg` breakpoint — widen the window or use desktop width.

## Exports 404

Assessment must be **published**. Paths resolve only under `data/exports/`.

## SQLite locked / multi-instance

Run exactly one replica and one Uvicorn worker. Do not enable horizontal autoscaling.
