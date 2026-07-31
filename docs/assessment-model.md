# Assessment model configuration

The SAFe assessment model is configuration-driven via:

`config/assessment/assessment_model.yaml`

## What admins can change without code

- Domain order (`domains[].order`)
- Practice order within a domain (`domains[].practices[].order`)
- Rubric wording, question/clarification seeds, evidence mappings
- Stop criteria, minimum confidence, influence policies
- Prompt templates, model defaults, voice defaults

Stable `key` values should remain stable once assessments exist in the database.

## Validation

Startup loads and validates the YAML with a strict Pydantic schema. Invalid configuration fails startup.

## Score secrecy

- `ai_candidate_score` is admin-only
- Participant coverage schemas omit candidate scores
- Published reports store admin final scores (or accepted candidate scores) only
