# Admin review and publication

Lifecycle: `interview_complete` → `admin_review` → `published`.

## Candidate scoring

- AI produces candidate scores (1.0–5.0) with named maturity levels
- Participant/host views never receive AI candidate scores
- Admin review shows AI vs final comparison

## Adjustments

- Changing a score requires a **rationale**
- Improvement actions can be edited before publish
- Enterprise Standards findings can be status-adjusted with observation/recommendation/admin notes; they never block publication and do not change SAFe scores
- Approve marks the package ready; publish creates an immutable versioned report (including a frozen enterprise-standards section)

## Evidence influence modes

Configured per assessment (`evidence_influence_mode`):

| Mode | Intent |
| --- | --- |
| `balanced` | Default blend of conversation + tooling evidence |
| `conversation_heavy` | Weight human interview higher |
| `tooling_heavy` | Weight Jira/ADO metrics higher |

Integration/collection failures are evidence **limitations**, not automatic low maturity.

## Exports

After publish:

- JSON and PDF under `data/exports/<assessment_id>/v<n>/`
- Download via `/api/assessments/{id}/export/{json|pdf}`
- Public results omit AI candidate scores
