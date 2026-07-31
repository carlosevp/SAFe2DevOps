# Product scope

## Product

**SAFe DevOps Adaptive Assessment** — a guided maturity assessment that combines team conversation with delivery-tool evidence to produce actionable SAFe DevOps insights.

## UX source of truth

The Figma Make frontend in this repository is the visual and interaction source of truth. Implementation phases must preserve its screens, flows, and design language unless a later ADR explicitly changes them.

## In scope for the pilot

- Adaptive assessment across **16 SAFe DevOps practices** (Continuous Exploration, Continuous Integration, Continuous Delivery, Release on Demand)
- Hidden evaluation during conversation (participants are not filling a traditional maturity form)
- **One Jira Cloud** environment
- **One Azure DevOps Services** environment
- Per assessment: **one representative Jira project** and **one representative ADO repository**
- Evidence snapshot from Jira/ADO for a configurable lookback window
- Workshop room with voice-to-text capture and typed notes
- Remote typed contributors (async inbox into the workshop)
- Adaptive next-best-question flow driven by coverage gaps + evidence
- Admin review before publication (adjust scores with rationale)
- Published outputs: radar, heatmap, maturity report, and improvement plan
- AI settings for transcription/model behavior defaults

## Out of scope for early phases

- Multi-tenant enterprise SSO beyond the pilot’s admin model
- Multiple simultaneous Jira or ADO environments
- Multi-replica horizontal scaling while SQLite is in use
- Broad redesign of the Figma UI
- Full historical analytics warehouse

## Deployment targets

| Environment | Platform | Notes |
| --- | --- | --- |
| Testing | Railway | Fast iteration, mounted volume for SQLite |
| Final | OpenShift | Production target with persistent volume |

## Persistence constraint

SQLite stored on persistent mounted storage. Exactly **one application replica** while SQLite is used.
