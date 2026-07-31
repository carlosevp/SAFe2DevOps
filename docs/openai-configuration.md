# OpenAI configuration

## Server-side only

Set `OPENAI_API_KEY` in the environment / Secret. Never put the long-lived key in frontend env vars or the browser.

## Models

| Setting | Default | Use |
| --- | --- | --- |
| `OPENAI_ASSESSMENT_MODEL` | `gpt-5.6-terra` | Interview + scoring (Responses API) |
| `OPENAI_TRANSCRIPTION_MODEL` | `gpt-4o-transcribe` | Realtime WebRTC voice via server-mediated SDP exchange (`gpt-realtime-whisper` requires manual stop / no VAD) |
| `OPENAI_REASONING_EFFORT` | `medium` | Reasoning effort for assessment model |

Runtime AI/voice settings can also be adjusted in **AI settings** (persisted server-side).

## Providers

| Env | Values | Behavior |
| --- | --- | --- |
| `INTERVIEW_PROVIDER` | `mock` (default), `live` | Deterministic mock vs OpenAI |
| Scoring | follows interview/live key availability | Mock scoring when not live |

## Voice

- Backend mints **ephemeral** Realtime credentials for the browser
- Long-lived API key never returned to the client
- Temporary audio stays under `/tmp` / working dirs unless retention is enabled

## Safety

- Interview and scoring prompts treat answers, remote contributions, and Jira/ADO text as untrusted
- Structured Outputs constrain model JSON
- Telemetry logs omit transcript bodies
