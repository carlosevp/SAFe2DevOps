# Manual transcription evaluation set

Use this checklist with **non-sensitive** practice recordings only. Do not commit production workshop audio.

## Scenarios

| ID | Scenario | Notes |
| --- | --- | --- |
| E1 | Quiet individual speaker | Close mic, quiet room |
| E2 | Group around conference table | Shared table mic if available |
| E3 | Distant speaker | Same laptop mic, speaker ~3m away |
| E4 | Background noise | HVAC / hallway noise |
| E5 | Technical terms and acronyms | SAFe, CI/CD, OpenShift, SonarQube, Snyk |
| E6 | Numbers and dates | Release dates, sprint numbers, versions |
| E7 | Pauses in long answers | 5–15s thinking pauses mid-answer |

## Script seeds (safe examples)

- "Our Continuous Integration pipeline runs unit tests on every pull request, then SonarQube quality gates before merge."
- "We deploy to OpenShift staging after Azure DevOps CI, watch observability dashboards, and can rollback or fix forward."
- "On March twelfth we released version two point four; the feature flag stayed off for the first forty-eight hours."

## Compare for each sample

1. Realtime live draft (`gpt-live-transcribe`)
2. Final refinement (`gpt-transcribe`)
3. Human reference transcript

## Track

| Metric | How |
| --- | --- |
| Missing words | Diff vs human reference |
| Truncated answers | Ends mid-sentence / shorter than audio |
| Empty transcripts | Live or final blank |
| Domain-term errors | SAFe / tool names wrong |
| Time to first live text | From Listening → first delta (ms) |
| Final refinement duration | Finish → refined text (ms) |

Record aggregates in the admin diagnostics panel (timings/failure rates only). Do not paste full transcripts into tickets that leave the org.
