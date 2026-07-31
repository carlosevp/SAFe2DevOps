# Figma screen map

Routing today is **client-side screen state** in `src/App.tsx` via `useState<Screen>`. There is no React Router dependency yet.

## Screens

| Screen key | File | Entry points | Notes |
| --- | --- | --- | --- |
| `welcome` | `src/screens/Welcome.tsx` | Default app state; logo click | Landing hero, start assessment, resume shortcuts |
| `integrations` | `src/screens/Integrations.tsx` | Header / admin nav | Mock Jira + ADO credential forms; timed “test connection” |
| `setup` | `src/screens/SetupWizard.tsx` | Welcome CTA | Multi-step wizard: team, Jira project, ADO repo, participation |
| `evidence` | `src/screens/EvidencePreview.tsx` | Setup completion | Confirms sample metrics from Jira/ADO |
| `workshop` | `src/screens/WorkshopRoom.tsx` | Evidence / Welcome resume | Voice mock transcript, coverage panel, remote inbox |
| `checkpoint` | `src/screens/Checkpoint.tsx` | Workshop overlay | Mid-session pause overlay on top of workshop |
| `remote-contributor` | `src/screens/RemoteContributor.tsx` | Welcome / workshop link | Minimal layout without main header chrome |
| `admin-review` | `src/screens/AdminReview.tsx` | Workshop completion path | Practice coverage, score adjust, publish |
| `results` | `src/screens/Results.tsx` | Admin publish | Radar, heatmap, report, improvement plan |
| `ai-settings` | `src/screens/AISettings.tsx` | Admin nav | Transcription + model defaults (local save toast) |

## Shared components

| Component | File | Role |
| --- | --- | --- |
| `Header` | `src/components/Header.tsx` | Brand mark, assessment status, dark mode, save & exit |
| `RadarChart` / `HeatmapChart` | `src/components/Charts.tsx` | Results and admin review visualizations |

## Design tokens

Defined in `src/index.css`:

- CSS variables for light/dark (`--background`, `--primary`, `--accent`, etc.)
- Tailwind v4 `@theme inline` palette: navy / teal / amber / slate scales
- Fonts: Instrument Serif (display), Inter (UI), JetBrains Mono (mono)

## Mocked / incomplete handlers (expected in Phase 1)

| Area | Behavior today |
| --- | --- |
| Sample practices & metrics | `src/data/sampleData.ts` |
| Integrations test/refresh | `setTimeout` status simulation |
| Workshop recording | Types a `MOCK_TRANSCRIPT` character-by-character |
| Adaptive questioning | Hardcoded `WORKSHOP_QUESTIONS` sequence |
| Remote contributions | Static `REMOTE_CONTRIBUTIONS` list |
| Admin publish | Delayed navigate to `results` |
| AI settings save | Local “saved” toast only |
| Setup copy-link | UI copy acknowledgement only |

No real `fetch` calls to backend or vendor APIs exist yet.

## Practice model (16)

From `SAMPLE_PRACTICES`:

**CE:** Hypothesis-Driven Development, Continuous Design, Continuous Exploration, Continuous Planning  
**CI:** Trunk-Based Development, Continuous Integration, Test-First Development, Non-Functional Requirements  
**CD:** Staging Environments, Continuous Deployment, Production Monitoring, Recover from Failures  
**RoD:** Release on Demand, Feature Toggles, Business Monitoring, Lean UX Lifecycle
