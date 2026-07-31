# OpenAI configuration

## Server-side only

Set `OPENAI_API_KEY` in the environment / Secret. Never put the long-lived key in frontend env vars or the browser.

## Models

| Setting | Default | Use |
| --- | --- | --- |
| `OPENAI_ASSESSMENT_MODEL` | `gpt-5.6-terra` | Interview + scoring (Responses API) |
| Live transcription | `gpt-live-transcribe` | Realtime WebRTC live draft (`turn_detection: null`, delay default `high`) |
| Final transcription | `gpt-transcribe` | One-shot accuracy pass on finished MediaRecorder upload |
| Text polish fallback | `gpt-4o-mini` | If audio refine fails, polish live draft for ASR/domain terms only |
| `OPENAI_REASONING_EFFORT` | `medium` | Reasoning effort for assessment model |

Transcription quality is controlled by **live delay** (higher = more accurate, slower partials) and vocabulary hints — not by assessment temperature.

Runtime AI/voice settings can also be adjusted in **AI settings** (persisted server-side).

## Providers

| Env | Values | Behavior |
| --- | --- | --- |
| `INTERVIEW_PROVIDER` | `mock` (default), `live` | Deterministic mock vs OpenAI |
| Scoring | follows interview/live key availability | Mock scoring when not live |

## Voice (two-pass)

1. Backend mints **ephemeral** Realtime credentials; browser POSTs SDP directly to OpenAI `/v1/realtime/calls`.
2. Live draft streams via WebRTC with assessment prompt/keywords.
3. Parallel MediaRecorder keeps audio in browser memory.
4. On Finish, audio uploads once to FastAPI for `gpt-transcribe` refinement, then temp audio is deleted unless retention is enabled.
5. Host edits confirmed text before assessment submit — never auto-submitted.

See `docs/voice-transcription-audit.md`.

## Safety

- Interview and scoring prompts treat answers, remote contributions, and Jira/ADO text as untrusted
- Structured Outputs constrain model JSON
- Telemetry logs omit transcript bodies, raw audio, and credentials
