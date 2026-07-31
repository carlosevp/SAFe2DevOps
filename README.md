# SAFe2DevOps

Adaptive SAFe DevOps maturity assessment. The product combines a guided team conversation with representative Jira Cloud and Azure DevOps Services evidence to produce a published maturity report and improvement plan.

## Current status

Phase 1 (this repository bootstrap):

- Figma Make frontend is the UX and interaction source of truth
- Frontend validates with TypeScript and a production Vite build
- Backend features are intentionally not implemented yet
- Architecture, scope, and implementation phases are documented under `docs/`

## Stack (planned)

| Layer | Choice |
| --- | --- |
| Frontend | React 19, Vite 8, TypeScript, Tailwind CSS v4 |
| Backend | Python API (foundation phase) |
| AI | OpenAI for adaptive questioning, transcription assist, and scoring drafts |
| Storage | SQLite on persistent mounted storage |
| Test deploy | Railway |
| Final deploy | OpenShift |
| Scale constraint | Exactly one application replica while SQLite is used |

## Frontend (Figma source)

Package manager: **pnpm** (see `.mise.toml` and `pnpm-lock.yaml`).

```bash
pnpm install
pnpm exec tsc --noEmit
pnpm run build
pnpm run dev
```

There is no lint script in the Figma scaffold yet (`oxfmt` is available via `pnpm run format`).

### Screen map

Client-side screen state in `src/App.tsx` (no router library yet):

| Screen key | Component | Purpose |
| --- | --- | --- |
| `welcome` | `Welcome` | Landing / assessment entry |
| `integrations` | `Integrations` | Jira + Azure DevOps admin config |
| `setup` | `SetupWizard` | Assessment scope wizard |
| `evidence` | `EvidencePreview` | Confirm representative evidence snapshot |
| `workshop` | `WorkshopRoom` | Voice/typed workshop room |
| `checkpoint` | `Checkpoint` | Mid-session overlay |
| `remote-contributor` | `RemoteContributor` | Remote typed contributions |
| `admin-review` | `AdminReview` | Admin review before publish |
| `results` | `Results` | Radar, heatmap, report, plan |
| `ai-settings` | `AISettings` | Transcription / model defaults |

See `docs/figma-screen-map.md` for the full map.

## Documentation

- [Product scope](docs/product-scope.md)
- [Figma screen map](docs/figma-screen-map.md)
- [Target architecture](docs/target-architecture.md)
- [Implementation plan](docs/implementation-plan.md)
- [ADR-001 Fresh build](docs/decisions/ADR-001-fresh-build.md)
- [ADR-002 SQLite persistent storage](docs/decisions/ADR-002-sqlite-persistent-storage.md)

## Safety

Never commit `.env` files, tokens, PATs, API keys, local databases, uploads, exports, `node_modules`, or build output. Use `.env.example` as the template.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
