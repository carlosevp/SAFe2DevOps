# Target architecture

## Goals

Ship a trustworthy pilot that:

1. Matches the Figma UX
2. Collects representative Jira/ADO evidence
3. Runs an adaptive workshop with voice + remote typed input
4. Produces admin-reviewed published maturity outputs
5. Deploys simply on Railway (test) and OpenShift (final)

## High-level shape

```text
┌────────────────────────────────────────────────────────────┐
│ Browser (React / Vite / Tailwind)                          │
│  Welcome → Setup → Evidence → Workshop → Admin → Results   │
└───────────────────────────┬────────────────────────────────┘
                            │ HTTPS JSON API
┌───────────────────────────▼────────────────────────────────┐
│ Application API (Python) — single replica                   │
│  Auth/session · Assessments · Evidence · Workshop · AI      │
│  Integrations · Admin review · Publication                  │
└───────┬─────────────────┬─────────────────┬────────────────┘
        │                 │                 │
        ▼                 ▼                 ▼
   SQLite (PVC)     Jira Cloud API    Azure DevOps API
   /data/*.sqlite   (read-only)       (read-only)
                          │
                          ▼
                     OpenAI APIs
              (transcribe / adaptive Q / draft scores)
```

## Frontend

- Keep Figma screens as the presentation layer
- Replace mocked handlers with API clients incrementally
- Introduce a real router only when deep-linking/share URLs require it (remote contributor link is a likely first need)

## Backend responsibilities

| Domain | Responsibility |
| --- | --- |
| Integrations | Store encrypted Jira/ADO credentials; test connection; list projects/repos |
| Assessments | Setup wizard persistence; scope; lookback; participation mode |
| Evidence | Snapshot metrics for one Jira project + one ADO repo |
| Workshop | Questions, transcripts, clarifications, coverage state, remote inbox |
| AI | Next-best question, coverage inference, draft scores/rationales |
| Admin | Review, adjust scores with rationale, publish |
| Results | Serve published radar/heatmap/report/plan |

## Persistence

- **SQLite** file on a persistent mounted volume (`DATABASE_PATH`)
- Exactly **one** app replica while SQLite is used (see ADR-002)
- No shared-network SQLite across multiple writers

## Integrations

- One Jira Cloud site
- One Azure DevOps Services organization
- Least-privilege read scopes only
- Credentials never returned in full to the browser after save

## Deployment

| Stage | Platform | Storage | Replicas |
| --- | --- | --- | --- |
| Test | Railway | Mounted volume | 1 |
| Final | OpenShift | PersistentVolumeClaim | 1 |

## Security boundaries

- Browser never holds raw Jira/ADO tokens or OpenAI keys
- Server masks secrets in admin UI
- Unpublished assessments restricted to admin/host roles
- Transcripts treated as sensitive organizational content
