# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Betty?

Betty is an AI voice companion for Australian truck drivers, built for the **Gemini Live Agent Challenge** hackathon (deadline March 16, 2026). She proactively calls drivers when safety systems detect fatigue, erratic driving, or approaching break limits, using Google Gemini Live API for real-time bidirectional voice conversations.

## Hackathon links

- DevPost: https://geminiliveagentchallenge.devpost.com/
- Resources: https://geminiliveagentchallenge.devpost.com/resources
- Google Cloud blog: https://cloud.google.com/blog/topics/training-certifications/join-the-gemini-live-agent-challenge
- Category: The Live Agent
- Prize pool: $80,000 (grand prize $25,000 + trip to Google Cloud Next '26)
- Requirements: Gemini model + Gen AI SDK or ADK + at least one Google Cloud service

## Commands

### Run the server
```bash
export GEMINI_API_KEY=your-key
python -m src.main
# Dashboard: http://localhost:8000/
# Driver phone: http://localhost:8000/static/driver.html?id=DRV001
```

### Run tests
```bash
# Unit tests (no API key needed)
pytest tests/test_triggers.py tests/test_memory.py tests/test_tools.py

# Automated two-session conversation (requires GEMINI_API_KEY)
python tests/test_conversation.py

# Live mic test (requires GEMINI_API_KEY + mic/speaker)
python tests/test_voice.py
```

### Deploy
```bash
export GEMINI_API_KEY=your-key
bash deploy.sh
```

## Architecture

### Call flow
Trigger event → `trigger_engine.assess_risk()` scores severity (0-1) → `call_manager.initiate_call()` → WebSocket notification to driver's browser → driver accepts → `ws_handler.handle_driver_call()` bridges browser audio ↔ Gemini Live session → Betty converses using system prompt built by `prompts.build_system_prompt()` → tool calls handled by `betty_tools.handle_tool_call()` → call ends, transcript preserved.

### Two-session simulation
`simulated_call.py` runs two Gemini Live sessions talking to each other — Betty and a simulated driver persona. Audio from one session is resampled and fed to the other. No mic needed.

### Audio protocol
- Browser → server: 16-bit PCM, 16 kHz mono (via AudioWorklet)
- Gemini output: 16-bit PCM, 24 kHz mono
- Resampling between 16k/24k done via NumPy linear interpolation

### Memory system
Encrypted cross-call memory in SQLite (`data/memory.db`). AES-256-GCM with HKDF-derived per-driver keys. Master key from `BETTY_MEMORY_KEY` env var. 14-hour TTL with auto-purge.

### Visual cards (`src/cards/`)
Pillow-rendered PNG cards (rest stop recommendations, shift wellness summaries, incident reports). Rest stop cards use Gemini Flash + Google Search grounding to describe real locations, then Imagen 4 to generate scenic backgrounds. Cards saved to `static/cards/` and broadcast via WebSocket.

### Tools Betty can call mid-conversation
Declared in `betty_tools.py`: `get_driver_hours`, `get_recent_events`, `escalate_to_manager`, `log_conversation_summary`, `assess_driver_mood`, `send_rest_stop_card`. The `FunctionResponse` must include `id=fc.id` (Google API requirement).

### Frontend
Two views sharing `style.css`: dashboard (`dashboard.html`/`dashboard.js`) for fleet managers, driver phone (`driver.html`/`driver.js`) for drivers. Both use WebSockets for real-time updates.

## Key conventions

- Config lives in `config/betty.yaml` — personality, escalation thresholds, trigger settings, Gemini model config
- Mock driver data in `src/data/mock_fleet.py` and `data/mock/sample_data.json`
- Driver personas for simulation in `data/mock/driver_personas.json`
- Video frames for fatigue camera simulation in `data/mock/videos/{driver_name}/`
- Sound effects in `static/sfx/`
- Environment variables: `GEMINI_API_KEY` (required), `BETTY_MEMORY_KEY` (for memory encryption)
- Gemini model: `gemini-2.5-flash-native-audio-latest` with voice `Aoede`
