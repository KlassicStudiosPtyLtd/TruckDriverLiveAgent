# Betty Build Report

## Project: Betty — AI Voice Companion for Truck Drivers

**Date:** 2026-03-01
**Status:** Complete rebuild for Gemini Live Agent Challenge hackathon (deadline March 16, 2026)

---

## Architecture Change: AWS Nova Sonic → Google Gemini Live API

The original Betty was built on AWS Nova Sonic + Amazon Connect. It has been completely rebuilt for the **Gemini Live Agent Challenge** hackathon using:

- **Voice Engine**: Google Gemini Live API (`gemini-2.0-flash-live-001`) with Aoede voice
- **Transport**: Browser WebSocket with AudioWorklet for PCM capture/playback (no third-party telephony)
- **Server**: FastAPI + Uvicorn
- **Stack**: 100% Google (Gemini Live API + Cloud Run)

The original `betty/` package is preserved for reference but no longer used. All new code lives under `src/`.

---

## Phase 1: Project Scaffolding + Voice Core

### Files Created/Rewritten
| File | Purpose |
|------|---------|
| `requirements.txt` | Replaced AWS deps with `google-genai>=1.0.0`. Kept FastAPI, uvicorn, pydantic, pyyaml, pyaudio, numpy |
| `config/betty.yaml` | Ported from `config.yaml` — replaced AWS/Bedrock/Connect config with Google Gemini config (model, voice, API key env var) |
| `src/__init__.py` | Package root |
| `src/voice/__init__.py` | Voice module |
| `src/voice/prompts.py` | Ported from `betty/voice/system_prompt.py` — kept the prompt text, context builders, speaks-first templates. Removed Pydantic model dependencies, uses plain strings for trigger types |
| `src/voice/gemini_live.py` | **Core new file.** `GeminiLiveSession` class wrapping `google-genai` SDK. ~130 lines replacing the 653-line `nova_sonic.py` |
| `tests/test_voice.py` | Standalone script: opens Gemini session, sends text, plays audio via PyAudio, streams mic input |

### Key Decisions
- `GeminiLiveSession` uses `google.genai.types.LiveConnectConfig` for session setup
- Audio: receives via `session.receive()` async generator, sends via `session.send()` with `LiveClientRealtimeInput`
- Tool call responses sent as `FunctionResponse` objects
- `_maybe_await()` helper handles both sync and async callbacks
- `output_audio_transcription` enabled by default for live transcript forwarding

---

## Phase 2: Tools + Mock Data

### Files Created
| File | Purpose |
|------|---------|
| `src/data/__init__.py` | Data module |
| `src/data/mock_fleet.py` | Ported from `betty/mock/driver_data.py` — simplified to inline dicts (no JSON file, no Pydantic models). `MOCK_DRIVERS` dict, `_initial_hours()`, `_initial_events()` |
| `src/tools/__init__.py` | Tools module |
| `src/tools/betty_tools.py` | Ported from `betty/voice/tools.py` — changed declaration format from Nova Sonic `toolSpec` to Gemini `types.FunctionDeclaration` with `types.Schema`. Same 4 tool handlers |
| `tests/test_tools.py` | Test tool calling in voice conversation — asks Betty about Mick's hours |

### Mock Drivers
| ID | Name | Route | Hours Driven | Status |
|----|------|-------|-------------|--------|
| DRV001 | Mick Thompson | Perth → Kalgoorlie (Great Eastern Hwy) | 3.5h | Mid-shift |
| DRV002 | Shazza Williams | Geraldton → Meekatharra (Murchison) | 4.25h | Approaching break |
| DRV003 | Davo Chen | Karratha → Port Hedland (Great Northern Hwy) | 1.75h | Fresh |

### Tool Declarations (Gemini format)
1. `get_driver_hours` — Break status, rest area info, shift remaining
2. `get_recent_events` — Fatigue/driving event history within N hours
3. `escalate_to_manager` — Fleet manager alert (low/medium/high urgency)
4. `log_conversation_summary` — Post-call record with fatigue assessment

---

## Phase 3: Browser Voice Bridge

### Files Created
| File | Purpose |
|------|---------|
| `src/main.py` | FastAPI app: mounts static files, registers all routes + WebSocket endpoints, health check, trigger API, dashboard API |
| `src/call/__init__.py` | Call module |
| `src/call/call_manager.py` | `CallManager` class: PendingCall tracking, driver/dashboard WebSocket registrations, `initiate_call()`, `accept_call()`, `end_call()`, notification broadcasting |
| `src/call/ws_handler.py` | **Critical file.** `/call/{driver_id}` WebSocket handler bridging browser PCM ↔ Gemini Live API. Builds system prompt with full driver context, creates `GeminiLiveSession` with tools, forwards audio bidirectionally |
| `static/audio-processor.js` | AudioWorklet: captures Float32 PCM from mic, converts to Int16, buffers 100ms chunks (1600 samples at 16kHz), posts to main thread |
| `static/driver.html` | Driver phone UI: dark theme, incoming call ring animation, accept/decline buttons, call timer, audio level indicator, live transcript area |
| `static/driver.js` | `DriverPhone` class: notification WS connection, mic capture via AudioWorklet (16kHz), queue-based PCM playback (24kHz) to avoid clicks/gaps, state management (idle/ringing/connected) |

### Audio Architecture
- **Mic capture**: `AudioContext({sampleRate: 16000})` → AudioWorklet → Int16 PCM → WebSocket binary frames
- **Playback**: WebSocket binary frames → Int16→Float32 conversion → `AudioContext({sampleRate: 24000})` with scheduled `BufferSource` playback (seamless, no gaps)
- **No audio transcoding** — browser `AudioContext` handles resampling natively

### WebSocket Protocol
- Browser sends: binary frames (raw 16-bit PCM 16kHz mono) or JSON `{"type": "hangup"}`
- Server sends: binary frames (raw 16-bit PCM 24kHz mono) or JSON `{"type": "transcript", ...}` / `{"type": "call_connected", ...}` / `{"type": "turn_complete"}`

---

## Phase 4: Triggers + Notifications

### Files Created
| File | Purpose |
|------|---------|
| `src/triggers/__init__.py` | Triggers module |
| `src/triggers/trigger_engine.py` | Event router: `assess_risk()` scores events (ported from `betty/orchestration/risk_assessor.py`), `assess_and_call()` initiates calls + notifies driver browser + broadcasts to dashboard |
| `src/triggers/fatigue_monitor.py` | Fatigue event processing and storage |
| `src/triggers/driving_monitor.py` | Erratic driving event processing and storage |
| `src/triggers/break_timer.py` | `BreakTimer` class: periodic async scheduler checking all drivers against break limits (ported from `betty/triggers/break_scheduler.py`) |

### Risk Scoring (ported from original)
- Base scores by severity: low=0.3, medium=0.6, high=0.9
- Fatigue type modifiers: head_nod +0.2, droopy_eyes +0.1, phone_use +0.1, distraction +0.05, smoking -0.05
- Erratic driving sub-type scores: rollover_intervention=0.95, excessive_sway=0.7, lane_deviation=0.5, harsh_braking=0.4
- G-force amplifiers: >0.5g +0.1, >0.8g +0.1
- Consecutive event escalation: 3+ events in 1 hour +0.2
- Priority mapping: score 0-1 → priority 1-5 (1=highest)

### Notification Flow
```
POST /api/triggers/trigger → assess_risk() → initiate_call()
  → notify_driver() via notification WS → driver browser rings
  → driver accepts → /call/{id} WS opens → Gemini session starts
  → broadcast_to_dashboard() via dashboard WS → live updates
```

### Endpoints Added to main.py
- `POST /api/triggers/trigger` — receive trigger events, assess risk, initiate calls
- `WS /driver/notifications/{driver_id}` — push incoming call notifications to driver browser
- `WS /dashboard/ws` — push real-time updates (transcripts, call events) to dashboard

---

## Phase 5: Dashboard + Polish

### Files Created
| File | Purpose |
|------|---------|
| `src/dashboard/__init__.py` | Dashboard module |
| `src/dashboard/routes.py` | Reserved for additional dashboard-specific logic |
| `static/style.css` | Shared styles for both views — ported CSS variables, layout, buttons, status badges, animations, toggles, responsive grid from `betty/dashboard/templates/index.html` |
| `static/dashboard.html` | Fleet manager UI: driver cards, trigger controls (fatigue/erratic/break/check-in), call status with timer, live transcription feed, event log |
| `static/dashboard.js` | Dashboard logic: WebSocket for real-time updates (transcripts, call events), trigger sending via fetch API, polling `/dashboard/api/status` every 3s, driver status rendering |

### Dashboard Features
- **Driver panel**: 3 drivers with real-time hours, break status, event counts, call status (idle/on call)
- **Call status**: Timer, status badge (idle/ringing/connected), end call button
- **Trigger controls**: Driver selector, fatigue event (6 types + 3 severity levels), erratic driving (4 sub-types), break limit, companion check-in
- **Live transcription**: Real-time text feed during active calls (via dashboard WebSocket)
- **Event log**: Timestamped, color-coded entries (triggers in blue, calls in green, transcripts in purple, escalations in red)
- **Real-time updates**: Dashboard WebSocket receives transcripts, call started/ended events; also polls for driver status

### Dashboard API Endpoints
- `GET /` — Serves dashboard.html
- `GET /dashboard/api/status` — Full system status (drivers, active calls, event log)
- `POST /dashboard/api/end-call/{driver_id}` — End an active call

---

## Phase 6: Deploy + Submit

### Files Created
| File | Purpose |
|------|---------|
| `Dockerfile` | Python 3.12-slim, installs deps, copies config/src/static, runs uvicorn on port 8080 |
| `deploy.sh` | `gcloud run deploy` with 600s timeout, 512Mi memory, session affinity (for WebSocket), passes `GEMINI_API_KEY` env var |
| `README.md` | Hackathon submission: quick start, demo flow, architecture, project structure, deploy instructions |
| `.dockerignore` | Excludes .venv, tests, docs, old betty/ dir, .env, .git, .claude |

---

## End-to-End Flow

```
1. Fleet manager opens dashboard (http://localhost:8000/)
2. Driver opens phone UI (http://localhost:8000/static/driver.html?id=DRV001)
3. Driver phone connects notification WebSocket → "Online"
4. Fleet manager selects Mick, clicks "Send Fatigue Event"
5. POST /api/triggers/trigger → risk assessment (score=0.70)
6. call_manager.initiate_call() creates PendingCall
7. notify_driver() pushes {"type": "incoming_call"} via notification WS
8. Driver phone rings (ring animation)
9. Driver clicks "Accept" → mic capture starts via AudioWorklet
10. /call/DRV001 WebSocket opens → call_manager.accept_call()
11. ws_handler builds system prompt with driver context + trigger context
12. GeminiLiveSession connects to Gemini Live API (Aoede voice, tools enabled)
13. Betty speaks first (trigger-specific greeting)
14. Audio streams bidirectionally: browser PCM ↔ server WS ↔ Gemini Live API
15. Betty can call tools (get_driver_hours, get_recent_events, escalate, log)
16. Transcripts forwarded to dashboard via dashboard WS
17. Driver hangs up → session closes → call_manager.end_call()
```

---

## Project Structure (New)

```
C:\Code\Betty/
├── src/                                # New Gemini-based application
│   ├── __init__.py
│   ├── main.py                         # FastAPI app, all routes + WebSocket endpoints
│   ├── voice/
│   │   ├── prompts.py                  # System prompt builder with dynamic context
│   │   └── gemini_live.py              # Gemini Live API session wrapper (~130 lines)
│   ├── tools/
│   │   └── betty_tools.py              # 4 Gemini function declarations + handlers
│   ├── data/
│   │   └── mock_fleet.py              # Mock driver profiles, hours, events (inline dicts)
│   ├── call/
│   │   ├── call_manager.py            # Call lifecycle tracking + WS registrations
│   │   └── ws_handler.py             # Browser-to-Gemini audio bridge
│   ├── triggers/
│   │   ├── trigger_engine.py          # Risk assessment + call initiation
│   │   ├── fatigue_monitor.py         # Fatigue event processing
│   │   ├── driving_monitor.py         # Erratic driving processing
│   │   └── break_timer.py            # Periodic break limit checker
│   └── dashboard/
│       └── routes.py                  # Dashboard-specific routes (reserved)
├── static/
│   ├── dashboard.html                 # Fleet manager UI
│   ├── dashboard.js                   # Dashboard logic + WebSocket
│   ├── driver.html                    # Driver phone UI (dark theme)
│   ├── driver.js                      # DriverPhone class + audio handling
│   ├── audio-processor.js             # AudioWorklet for mic capture
│   └── style.css                      # Shared styles
├── config/
│   └── betty.yaml                     # Configuration (Gemini model, voice, thresholds)
├── tests/
│   ├── test_voice.py                  # Standalone mic/speaker voice test
│   └── test_tools.py                 # Tool calling voice test
├── betty/                             # Original AWS-based code (preserved, not used)
├── requirements.txt                   # Python dependencies (google-genai, fastapi, etc.)
├── Dockerfile                         # Cloud Run deployment
├── deploy.sh                          # gcloud run deploy script
├── .dockerignore                      # Excludes old code + dev files
├── README.md                          # Hackathon submission
└── BUILD_REPORT.md                    # This file
```

---

## What Was Ported vs Written Fresh

| Source File | Ported To | What Changed |
|---|---|---|
| `betty/voice/system_prompt.py` | `src/voice/prompts.py` | Removed Pydantic/config deps, plain string trigger types, same prompt text + context builders |
| `betty/voice/tools.py` | `src/tools/betty_tools.py` | Changed `toolSpec` format to Gemini `FunctionDeclaration` + `Schema`. Same 4 handlers |
| `betty/mock/driver_data.py` | `src/data/mock_fleet.py` | Simplified to inline dicts (no JSON file, no Pydantic models). Plain dict returns |
| `betty/orchestration/risk_assessor.py` | `src/triggers/trigger_engine.py` | Same scoring logic, inline instead of separate module |
| `betty/triggers/break_scheduler.py` | `src/triggers/break_timer.py` | Same async scheduler pattern, removed config dependency |
| `betty/dashboard/templates/index.html` | `static/dashboard.html` + `style.css` | CSS ported to shared stylesheet, Jinja2 templates replaced with static HTML, JS extracted to `dashboard.js` |
| `betty/voice/nova_sonic.py` (653 lines) | `src/voice/gemini_live.py` (~130 lines) | **Written fresh** — completely different SDK and protocol |
| N/A | `src/call/ws_handler.py` | **Written fresh** — browser WebSocket ↔ Gemini bridge |
| N/A | `src/call/call_manager.py` | **Written fresh** — simplified from original orchestration/call_manager.py |
| N/A | `static/driver.html` + `driver.js` | **Written fresh** — browser phone UI with AudioWorklet |
| N/A | `static/audio-processor.js` | **Written fresh** — AudioWorklet for PCM capture |

---

## Key Technical Decisions

1. **No audio transcoding** — Browser `AudioContext({sampleRate: 16000})` handles resampling natively
2. **Old `betty/` package preserved** — not deleted, just not imported. Available for reference
3. **Queue-based audio playback** — `driver.js` schedules `BufferSource` nodes with `_nextPlayTime` to avoid clicks/gaps from per-chunk creation
4. **Session reconnection deferred** — 10-min Gemini session limit unlikely to be hit in demo
5. **No Pydantic models in new code** — plain dicts for simplicity and speed. Only `TriggerRequest` in main.py uses Pydantic for API validation
6. **Single main.py** — all routes in one file for hackathon simplicity (no router splitting)

---

## Next Steps

1. **Install deps** — `pip install -r requirements.txt`
2. **Set API key** — `export GEMINI_API_KEY=your-key`
3. **Test voice** — `python tests/test_voice.py` (requires mic/speaker + API key)
4. **Run server** — `python -m src.main` → open dashboard + driver phone
5. **End-to-end test** — trigger from dashboard → driver phone rings → accept → conversation
6. **Deploy** — `bash deploy.sh` → Cloud Run URL with WebSocket support
7. **Demo video** — record the full flow for hackathon submission
