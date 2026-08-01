# Detailed Assessment Review — design

Baseline: `bbe953222eae37820f6ec245cbe80b31a8cf97cb`.

## Current concise report (preserve)

Existing publication flow (`PublicationService.publish`):

- Versioned `published_reports` row
- JSON fields: radar, heatmap, scores, improvement_plan, strengths/gaps/limitations, enterprise_standards
- Concise PDF (maturity + enterprise summary + consolidated improvement plan)
- Public JSON export without AI candidate comparison / numeric enterprise scores
- Host UI (`Results.tsx`): overview, radar/heatmap, improvement horizons, enterprise summary

**Do not replace** the consolidated improvement plan or overview brevity.

## Gap

There is no structured long-form narrative layer. `summary_markdown` / `chart_summary` are short. Admin review edits scores and actions but not multi-section domain/practice narratives.

## Target product areas (published UI)

1. Overview (existing, concise)
2. Detailed Review (new)
3. Improvement Plan (existing, concise + roadmap enrichment context)
4. Enterprise Standards (existing section, keep SAFe-separated)
5. Evidence and Limitations (expand from current limitations list)

## Persistence approach

Prefer extending published-report JSON rather than many new tables:

- Add nullable `detailed_report_json` on `published_reports` (and draft storage on `assessment_reviews.detailed_report_json`)
- Add nullable `detailed_report_draft_json` / edit overlay if admin edits must be preserved separately before publish
- Legacy reports without the field load with `detailed_review: null` and UI hides or shows “not generated”

Migration required for the new columns only.

## Schema: `DetailedAssessmentReport`

```json
{
  "schema_version": 1,
  "methodology": {},
  "executive_narrative": {},
  "domain_reviews": [],
  "practice_reviews": [],
  "cross_cutting_themes": [],
  "enterprise_standards_review": {},
  "roadmap_context": [],
  "evidence_limitations": {},
  "generation_metadata": {
    "model_name": "",
    "generated_at": "",
    "section_statuses": {},
    "incomplete": false,
    "warnings": []
  }
}
```

Every factual claim carries internal `source_refs` with typed keys:

- `interview_turn`, `evidence_metric`, `practice_coverage`, `enterprise_finding`, `admin_observation`

Participant UI never shows raw DB IDs; admin evidence navigation may resolve them server-side.

Claim kinds (required labeling):

- `observed_evidence`
- `assessment_interpretation`
- `illustrative_example`
- `recommendation`

## Generation pipeline (staged)

Uses configured assessment model (`OPENAI_ASSESSMENT_MODEL` / interview provider settings). Mock provider returns deterministic demo content.

1. Build normalized evidence dossier (interview paraphrases, aggregated metrics, scores, enterprise findings, admin notes)
2. Generate domain reviews one domain at a time
3. Practice drill-downs in bounded groups (e.g. 4 practices)
4. Cross-cutting synthesis
5. Executive narrative from validated sections
6. Validate references, practice/standard keys, score consistency, section lengths
7. Deduplicate recommendations vs existing action plan (do not discard action plan)
8. Compose final report; mark incomplete sections if partial failure

Partial failure: keep successful sections, allow admin Retry per section, never publish incomplete detailed report without warning flag.

## Privacy defaults

- Paraphrase participant answers
- Aggregate Jira/ADO metrics only
- No issue titles, commit messages, PR names, usernames, emails
- Future admin toggle for named evidence — default off

## Admin workflow additions

- Review/edit sections, regenerate one section or full detailed report
- Mark illustrative example unsuitable
- Preview HTML/PDF including detailed sections
- Accept before publish

## PDF / JSON

PDF order: cover/scope → executive summary → radar/heatmap → key actions → domain reviews → practice drill-downs → enterprise → roadmap/KPIs → evidence/limitations.

JSON export adds `detailed_review` object; omit or null for legacy.

## Tests

Validation, grounding, redaction, partial recovery, section retry, admin edit, publish, legacy compat, HTML/PDF/JSON, action-plan preservation, enterprise/SAFe separation, deterministic demo mock.
