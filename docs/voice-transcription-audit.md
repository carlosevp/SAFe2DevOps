# Voice transcription audit and repair

**Date:** 2026-07-31  
**Scope:** SAFe DevOps Adaptive Assessment in-room workshop voice path

## Previous architecture (pre-repair)

```
Browser mic (getUserMedia, unconstrained)
  → RTCPeerConnection audio track
  → OpenAI Realtime /v1/realtime/calls (ephemeral key from FastAPI)
  → data-channel transcription.delta / .completed
  → single partial/final string buffers (no item_id)
  → WorkshopRoom textarea
```

- No MediaRecorder local backup
- No second-pass file transcription
- No domain prompt/keywords
- Default model often `gpt-4o-transcribe` with `voice_stop_mode=manual` (turn detection omitted)
- Finish called `input_audio_buffer.commit` then immediately tore down WebRTC

## Phase 1 findings

### 1. Browser capture

| Item | Previous | Notes |
| --- | --- | --- |
| API | `getUserMedia` + WebRTC track | No MediaRecorder |
| Constraints | `{ audio: true }` fallbacks | No echo/noise/AGC; "Invalid constraint" workarounds for embedded previews |
| MIME / codec | WebRTC-negotiated (Opus) | App never selected MIME |
| Sample rate / channels | Browser defaults | Not forced |
| Chunk duration | N/A (continuous track) | — |

### 2. Transport

| Item | Previous |
| --- | --- |
| Path | Direct browser → OpenAI WebRTC (WHIP SDP POST) |
| Backend | Mint ephemeral `client_secrets` only |
| Upload | Stub temp-audio register (empty files); never used for bytes |
| Streaming | Continuous; reconnect lost in-flight audio |
| Gaps | Yes — disconnect/reconnect without local buffer |

### 3. OpenAI configuration

| Item | Previous |
| --- | --- |
| Session type | `transcription` |
| Model | Admin `transcription_model` (often `gpt-4o-transcribe`) |
| Connection | Ephemeral key + browser SDP to `/v1/realtime/calls` |
| Language | Optional singular `language` / `languages` for live model |
| Prompt / keywords | Not set |
| Delay | Not set |
| Turn detection | Omitted in manual mode; VAD only if admin enabled |
| Audio format | Implicit WebRTC |

### 4. Transcript event processing

| Item | Previous defect |
| --- | --- |
| Deltas | Appended to one `partialTranscript` string |
| Completed | Appended to `finalTranscript`, cleared partial |
| `item_id` | **Ignored** — out-of-order completions scramble/drop text |
| Finish | Commit then teardown before completed events |
| Pause | Mute track (`enabled=false`) |
| Restart | Preserved prior final text |

### 5. Performance / reliability root causes

1. **Wrong live model + manual stop:** `gpt-4o-transcribe` without turn detection largely waits for commit → slow/empty live draft until Finish.
2. **Finish race:** teardown before `transcription.completed` → truncated long answers.
3. **No `item_id` reconciliation:** missing/overwritten segments under multi-turn events.
4. **No local recording / second pass:** no recovery when Realtime drops words.
5. **No domain context:** SAFe/DevOps/tooling terms under-recognized.
6. **Weak capture constraints:** room mics without noise suppression / far-field guidance.
7. **Temp audio stub:** retention setting created empty files, not real uploads.

## Changes made (two-pass repair)

### New architecture

```
PASS 1 (live draft)
  getUserMedia (echoCancellation, noiseSuppression, autoGainControl, channelCount:1)
  → MediaStreamTrack → RTCPeerConnection (direct to OpenAI)
  → gpt-live-transcribe, turn_detection: null, delay, languages, prompt, keywords
  → item_id-keyed provisional/completed state → "Live draft" UI

PASS 2 (final accuracy) — parallel local record
  same MediaStream → MediaRecorder (webm/opus or browser-compatible)
  → keep Blob in memory (no continuous upload)
  → on Finish: stop recorder, freeze live draft, upload once to FastAPI
  → POST /v1/audio/transcriptions with gpt-transcribe (+ prompt/keywords/languages)
  → replace provisional with refined text (editable)
  → delete temp audio unless retain_source_audio
```

### Models / defaults

| Setting | Default |
| --- | --- |
| Live model | `gpt-live-transcribe` |
| Final model | `gpt-transcribe` |
| Live delay | `low` |
| Expected languages | `["en"]` |
| Final refinement | enabled |
| Audio retention | disabled |

### UX states

Connecting microphone → Ready → Listening → Paused → Live draft → Finishing recording → Refining transcript → Transcript ready / Refinement failed (live draft retained) → Disconnected / Permission denied.

### Security

- Long-lived `OPENAI_API_KEY` never returned to the browser
- Only short-lived ephemeral Realtime secrets reach the client
- Diagnostics never log raw audio, full transcripts, or credentials

## Known remaining limitations

- Distant speakers on a laptop mic remain unreliable; pre-workshop mic test is advisory only.
- Group overlapping speech is not diarized.
- Live draft quality depends on OpenAI Realtime availability and network ICE success.
- Detailed transcript diagnostics are development-oriented and off by default in production.
- Manual evaluation samples must not include sensitive production recordings.

## Manual evaluation set

See `docs/voice-transcription-eval.md`.
