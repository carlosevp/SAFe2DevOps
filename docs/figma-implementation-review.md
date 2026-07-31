# Figma implementation review

Review date: 2026-07-31  
Source of truth: Figma Make React UI in `frontend/src` (not a generic component kit).

## Verdict

Visual language remains Figma Make: navy/teal palette, Instrument Serif for hero/questions, custom cards/inputs, Lucide icons, light/dark CSS variables. There is **no** shadcn/Radix dashboard shell. Behavior has evolved beyond Phase‑1 mocks (API wiring); those behavioral differences below are **intentional**, not a design replacement.

## Design tokens

- `frontend/src/index.css`: `:root` / `.dark` CSS variables, Tailwind v4 `@theme inline`, navy/teal/amber/slate scales
- Fonts: Instrument Serif (display), Inter (UI), JetBrains Mono
- Motion: fade-in, slide-in-right, pulse-ring, typing-dots

## Shared chrome

| Piece | Fidelity | Notes |
| --- | --- | --- |
| `Header` | High | Brand mark, status pill, dark toggle, Save & exit |
| `Charts` | High | Custom SVG radar + heatmap (not chart-library dashboards) |
| `App.tsx` | High | Client `useState<Screen>` routing (no React Router) |

## Per-screen fidelity

| Screen | Fidelity | Light/dark | Responsive | Intentional deviations |
| --- | --- | --- | --- | --- |
| Welcome | High | Yes | Good | Resume/admin shortcuts may open screens without persisted assessment id |
| Integrations | High | Yes | Single column | Live save/test/catalog APIs; secrets never re-displayed |
| Setup wizard | High | Yes | Good | Creates assessment + sources via API; invite “copy link” UI still illustrative (real invites in workshop) |
| Evidence preview | High | Yes | Good | Live snapshot confirm / start interview |
| Workshop room | High | Yes | **Side panels hide below `lg`** | Live interview, voice WebRTC, remote inbox polling |
| Adaptive checkpoint | High | Yes | Good | Loads checkpoint API; finish → admin review |
| Remote contributor | High | Dark inherits only (no toggle) | Good | Requires `?invite=` signed token |
| Host contribution inbox | High | Yes | Tied to workshop `lg+` panels | Include/Defer/Dismiss APIs |
| Admin review | High | Mostly; some light success fills | Nav scrolls on mobile | Evidence/Transcript nav stubs are thin |
| Published results | High | Yes + print | Good | Public UUID results + PDF/JSON export |
| AI / voice settings | High | Yes | Good | Model/voice persist via API; some threshold toggles remain local UI-only |

## Light / dark gaps (accepted for pilot)

- Header status pills use fixed light greens/blues
- Remote contributor shell has no theme toggle
- Occasional hardcoded light success button fills

## Responsive gaps (accepted for pilot)

- Workshop coverage + contribution inbox columns are `hidden lg:block` — primary mobile gap

## Stale notes cleaned up

`docs/figma-screen-map.md` Phase‑1 “no fetch / mock only” claims are outdated; see this document for current intentional deviations.

## Non-goals

- Do not replace Figma screens with generic dashboard kits
- Do not introduce React Router solely for fidelity
