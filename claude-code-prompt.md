# Claude Code Prompt — Betty: AI Voice Companion for Truck Drivers

## How to Use This File

Copy the prompt below into Claude Code. Make sure the `betty-build-plan.md` file is in your project root directory so Claude Code can reference it.

Start by creating a new project directory, place both this file and the build plan in it, then run Claude Code from that directory.

```bash
mkdir betty
cd betty
# Copy betty-build-plan.md into this directory
# Then start Claude Code
claude
```

---

## The Prompt

Paste everything below the line into Claude Code:

---

Read the file `betty-build-plan.md` in this directory. This is a comprehensive build plan for a hackathon project. I'll summarise the key points below, but the build plan has all the architectural detail, project structure, system prompts, data models, config schema, and timeline.

## Project: Betty — AI Voice Companion for Truck Drivers

### What We're Building
Betty is a proactive AI voice agent for truck drivers, powered by Amazon Nova 2 Sonic (speech-to-speech model via Amazon Bedrock). She monitors safety telemetry from truck fleets and places outbound phone calls to drivers when intervention is needed. She also serves as a companion for lonely drivers on long hauls.

### Key Points
- **Language:** Python 3.12
- **Web Framework:** FastAPI
- **Voice AI:** Amazon Nova 2 Sonic via Bedrock bidirectional streaming API (`InvokeModelWithBidirectionalStream`)
- **Telephony:** Amazon Connect for outbound calls (with Twilio as backup if Connect is too complex)
- **Dashboard:** Simple web UI (HTML/JS or Streamlit) for simulating triggers and monitoring calls
- **Config:** YAML-based configuration for all tuneable parameters (escalation mode, thresholds, memory toggle, etc.)
- **This is a hackathon project** — the deadline is March 16, 2026. Prioritise a working demo over perfection. Simulated triggers are fine. Mock data for driver hours API is fine.

### Triggers That Cause Betty to Call a Driver
1. **Fatigue camera email** — SMTP email with fatigue event details (droopy eyes, distraction, yawning, etc.) with severity levels
2. **Erratic driving webhook** — HTTP POST with telematics data (lane deviation, harsh braking, rollover intervention, g-forces)
3. **Approaching mandatory break limit** — Scheduled check against mock driver hours API

### Betty's Personality
- Female, named Betty, warm and motherly
- Short conversational responses (2-3 sentences)
- Gently assesses fatigue without being clinical
- Can escalate to a human Fleet Manager (configurable: announced or silent)
- Cross-call memory within a shift (configurable: on/off)

### Nova 2 Sonic Features We Need to Use
- Bidirectional streaming for real-time voice
- Tool calling (get_driver_hours, get_recent_events, escalate_to_manager, log_conversation_summary)
- Async tool execution (conversation continues while tools run)
- Background noise robustness (truck cab environment)
- Expressive female voice

### What I Need You to Do

Please build this project following the structure and architecture in `betty-build-plan.md`. Work through it in this order:

**Step 1: Project scaffolding**
- Set up the project structure as defined in the build plan
- Create `requirements.txt` with all dependencies
- Create `config.yaml` with all configurable parameters (see Section 5 of build plan)
- Create Pydantic models for all event types and data structures
- Create the config loader

**Step 2: Mock data layer**
- Mock driver profiles (at least 3 drivers with realistic Australian names, vehicle details, current status)
- Mock driver hours data (hours driven, time until mandatory break, nearest rest area)
- Mock event history (recent fatigue and driving events per driver)
- All mock data should be realistic for Australian long-haul trucking

**Step 3: Nova 2 Sonic voice integration**
- Implement the bidirectional streaming client for Nova 2 Sonic via Bedrock
- Build Betty's system prompt with dynamic context injection (the build plan has a detailed draft)
- Implement the tool definitions and handlers
- Implement cross-call memory (session store, configurable on/off)
- Make it testable locally first (microphone/speaker) before telephony

**Step 4: Trigger ingestion**
- Email parser for fatigue camera alerts (use `aiosmtpd` for a local SMTP receiver for demo purposes)
- FastAPI webhook endpoint for telematics events
- Break limit scheduler (periodic check against mock driver hours)
- Risk assessor that scores events and decides whether to initiate a call

**Step 5: Orchestration**
- Context builder that assembles Betty's briefing from driver data + event data + config
- Call manager (initiate, track, end calls)
- Escalation logic (configurable thresholds, manager notification via webhook/log)

**Step 6: Telephony**
- Amazon Connect outbound call integration
- Bridge audio between Connect and Nova 2 Sonic
- If Amazon Connect is too complex, implement Twilio as alternative
- As absolute fallback, support direct microphone/speaker mode for demo

**Step 7: Dashboard**
- Simple web UI served by FastAPI
- Driver selector dropdown
- Trigger buttons (fatigue event with severity/type, erratic driving with sub-type, break limit warning)
- Live status panel (call status, duration, event log, escalation status)
- Configuration panel for key settings

### Important Technical Notes
- The Nova 2 Sonic model is accessed via `amazon.nova-sonic-v1:0` model ID in Bedrock (check if nova-2-sonic has a different model ID and use that if available)
- Region: `us-east-1`
- The bidirectional streaming API uses HTTP/2 protocol
- Nova 2 Sonic supports 8kHz telephony audio input natively
- For tool calling, Nova 2 Sonic supports async execution — the model continues talking while tools run in background
- All configurable parameters should come from `config.yaml`, never hardcoded

### Code Quality Guidelines
- Type hints on all functions
- Docstrings on all classes and public methods
- Use async/await throughout (FastAPI + async Bedrock calls)
- Clean separation of concerns as per the project structure
- Comprehensive error handling (especially around Bedrock API calls and telephony)
- Logging throughout (use Python `logging` module)
- Keep it clean but remember this is a hackathon — working code beats perfect code

Start with Step 1 and work through sequentially. After each step, confirm what you've built and ask if I want to review before moving on. Let's go!
