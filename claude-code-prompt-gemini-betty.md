# Claude Code Prompt: Betty — Gemini Live Agent for Truck Driver Safety

## Project Overview

Build "Betty", a proactive AI voice companion for truck drivers, for the **Gemini Live Agent Challenge** hackathon (deadline: March 16, 2026 @ 5:00 PM PDT). Betty is a warm, motherly voice agent that calls drivers when safety triggers fire (fatigue detection, erratic driving, approaching mandatory break limits) and is also available for companionship calls. This targets the **"Live Agents" category** — real-time voice interaction with interruption handling.

**Hackathon requirements:**
- Must use Gemini Live API or ADK
- Must use Google GenAI SDK or ADK
- Must use at least one Google Cloud service
- Must be deployed on Google Cloud
- Deliverables: public repo, architecture diagram, <4min demo video, proof of GCP deployment

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| Voice AI | Gemini Live API (native audio) via `google-genai` SDK |
| Model | `gemini-2.5-flash-native-audio-preview-12-2025` |
| Voice | "Aoede" (warm female — test alternatives: "Kore", "Leda") |
| Web Framework | FastAPI + WebSockets |
| Driver Interface | WebRTC browser-based voice (no third-party telephony needed) |
| Cloud | Google Cloud Run (backend), Cloud Logging |
| Config | YAML-based configuration |
| Frontend | Dashboard (HTML/JS) — fleet manager view + driver "phone" simulator |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TRIGGER LAYER                            │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ Fatigue Email │  │ Erratic Drive│  │ Break Timer        │   │
│  │ (SMTP mock)  │  │ (Webhook)    │  │ (Countdown)        │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘   │
│         └──────────────────┼──────────────────┘               │
│                            ▼                                    │
│              ┌─────────────────────────┐                       │
│              │   FastAPI Orchestrator   │                       │
│              │   (Event Router)         │                       │
│              └──────┬──────────┬───────┘                       │
│                     │          │                                │
│                     ▼          ▼                                │
│    ┌────────────────────┐  ┌──────────────────────────┐       │
│    │ Fleet Manager       │  │ Driver "Phone" UI        │       │
│    │ Dashboard           │  │ (Browser tab/mobile)     │       │
│    │ - Trigger simulator │  │ - Incoming call alert    │       │
│    │ - Live call monitor │  │ - WebSocket audio stream │       │
│    │ - Transcription     │  │ - Accept/decline call    │       │
│    │ - Config editor     │  │ - Mic + speaker via      │       │
│    │ - Event log         │  │   Web Audio API          │       │
│    └────────────────────┘  └──────────┬───────────────┘       │
│                                       │                        │
│                                       ▼                        │
│              ┌──────────────────────────────────┐              │
│              │   Gemini Live API Session         │              │
│              │   (Bidirectional Audio over WS)   │              │
│              │   + Function Calling (Tools)      │              │
│              │   + Audio Transcription            │              │
│              └──────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘

Two browser views (can be side-by-side in demo video):
  LEFT:  Fleet Manager Dashboard — shows triggers, monitoring, transcription
  RIGHT: Driver's "Phone" — simulates the in-cab device receiving Betty's call
```

---

## Project Structure

```
betty/
├── README.md                    # Hackathon submission README with spin-up instructions
├── requirements.txt
├── Dockerfile
├── deploy.sh                    # Automated GCP deployment (bonus points)
├── config/
│   └── betty.yaml               # All configurable parameters
├── src/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── gemini_live.py       # Gemini Live API session manager
│   │   └── prompts.py           # Betty's system prompt and persona
│   ├── call/
│   │   ├── __init__.py
│   │   ├── call_manager.py      # Manages active calls, session lifecycle
│   │   └── ws_handler.py        # WebSocket handler: browser ↔ Gemini audio bridge
│   ├── triggers/
│   │   ├── __init__.py
│   │   ├── trigger_engine.py    # Event router
│   │   ├── fatigue_monitor.py   # Fatigue camera email parser
│   │   ├── driving_monitor.py   # Erratic driving webhook handler
│   │   └── break_timer.py       # Hours-of-service countdown
│   ├── tools/
│   │   ├── __init__.py
│   │   └── betty_tools.py       # Function declarations for Gemini
│   ├── data/
│   │   ├── __init__.py
│   │   └── mock_fleet.py        # Mock driver/vehicle/telemetry data
│   └── dashboard/
│       ├── __init__.py
│       └── routes.py            # Dashboard + driver UI API routes
├── static/
│   ├── dashboard.html           # Fleet Manager dashboard UI
│   ├── driver.html              # Driver "phone" UI (receives calls)
│   ├── style.css
│   ├── dashboard.js             # Dashboard logic
│   └── driver.js                # Driver phone logic (Web Audio API + WebSocket)
├── tests/
│   ├── test_voice.py            # Standalone mic/speaker test
│   ├── test_tools.py            # Tool calling verification
│   └── test_triggers.py         # Trigger simulation tests
└── docs/
    └── architecture.png         # Architecture diagram for submission
```

---

## Implementation Details

### 1. Gemini Live API Session (`src/voice/gemini_live.py`)

This is the core voice engine. Use the `google-genai` Python SDK (NOT raw WebSockets).

**Install:** `pip install google-genai pyaudio`

**Critical SDK patterns:**

```python
import asyncio
from google import genai
from google.genai import types

# Initialize client
# For Google AI Studio (development):
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# For Vertex AI (production/deployment):
# Set env vars: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, GOOGLE_GENAI_USE_VERTEXAI=True
# client = genai.Client()

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

# Betty's voice and audio config
config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Aoede"  # warm female voice
            )
        )
    ),
    system_instruction=BETTY_SYSTEM_PROMPT,
    tools=[betty_tool_declarations],
    # Enable affective dialog for emotional awareness
    # enable_affective_dialog=True,  # if using v1alpha API
)

# Connect and stream
async with client.aio.live.connect(model=MODEL, config=config) as session:
    # Betty speaks first (proactive greeting)
    await session.send_client_content(
        turns=types.Content(
            role="user",
            parts=[types.Part(text="<TRIGGER_CONTEXT_INJECTED_HERE>")]
        )
    )
    
    # Receive audio response
    async for response in session.receive():
        if response.server_content:
            if response.data is not None:
                # PCM audio data — 24kHz, 16-bit, mono
                # Send to browser WebSocket or speaker
                pass
            if response.server_content.interrupted:
                # Driver interrupted Betty — handle gracefully
                pass
        if response.tool_call:
            # Handle function calls
            # Execute the tool, then send response back
            await session.send_tool_response(
                function_responses=[...]
            )
```

**Audio format specs:**
- Gemini input: 16kHz, 16-bit PCM, mono
- Gemini output: 24kHz, 16-bit PCM, mono
- Browser captures: typically 44.1kHz or 48kHz via Web Audio API — MUST downsample to 16kHz PCM before sending to Gemini
- Browser playback: Web Audio API can play any sample rate — decode Gemini's 24kHz PCM directly

**Session limits:** Max 10 minutes per session. For longer calls, implement session handoff (save context, reconnect).

### 2. Betty's Persona & System Prompt (`src/voice/prompts.py`)

```python
BETTY_SYSTEM_PROMPT = """You are Betty, a warm and caring voice companion for truck drivers. 
You speak like a supportive, experienced colleague who genuinely cares about driver safety and wellbeing.

Your personality:
- Warm, motherly, but never patronizing
- Uses casual Australian English (the drivers are Australian)
- Keeps responses SHORT — 2 to 3 sentences max. You're on a voice call, not writing an essay
- Asks open-ended questions to keep the driver talking (this fights fatigue)
- Knows trucking terminology naturally

Your capabilities (use the provided tools):
- Check a driver's logged hours and remaining drive time
- Review recent safety events (harsh braking, speeding, fatigue alerts)
- Escalate concerns to the Fleet Manager if the driver seems impaired
- Log a summary of each conversation for safety records

IMPORTANT RULES:
- NEVER diagnose medical conditions
- If the driver sounds genuinely distressed or mentions self-harm, immediately escalate to the fleet manager
- If fatigue is detected, gently suggest rest stops — never demand or threaten
- You can be interrupted — that's fine, just pick up naturally
- Don't use lists, bullet points, or any visual formatting — this is a voice conversation
"""
```

For different trigger types, inject context before the conversation:
- **Fatigue trigger:** "The fatigue monitoring camera just detected signs of drowsiness for driver {name} in truck {id}. Call them to check in warmly."
- **Erratic driving:** "Driver {name}'s truck just recorded {event_type} at {location}. Reach out to see if they're okay."
- **Break approaching:** "Driver {name} has been driving for {hours} hours. Their mandatory break is in {remaining} minutes."
- **Companionship:** "Driver {name} requested a chat. They've been on the road for {hours} hours."

### 3. Function Calling / Tools (`src/tools/betty_tools.py`)

**CRITICAL: In Gemini Live API, function calling is NOT automatic. You must handle tool responses manually.**

```python
from google.genai import types

# Tool declarations
get_driver_hours_decl = {
    "name": "get_driver_hours",
    "description": "Get the current driver's logged driving hours, remaining legal drive time, and time until mandatory rest break.",
    "parameters": {
        "type": "object",
        "properties": {
            "driver_id": {
                "type": "string",
                "description": "The driver's ID"
            }
        },
        "required": ["driver_id"]
    }
}

get_recent_events_decl = {
    "name": "get_recent_events",
    "description": "Get recent safety events for a driver including harsh braking, speeding violations, fatigue camera alerts, and rollover warnings.",
    "parameters": {
        "type": "object",
        "properties": {
            "driver_id": {"type": "string", "description": "The driver's ID"},
            "hours_back": {"type": "integer", "description": "How many hours back to check. Default 4."}
        },
        "required": ["driver_id"]
    }
}

escalate_to_manager_decl = {
    "name": "escalate_to_manager",
    "description": "Escalate a safety concern to the fleet manager. Use when the driver appears impaired, distressed, or refusing to take a required break. Can be silent (driver not told) or announced.",
    "parameters": {
        "type": "object",
        "properties": {
            "driver_id": {"type": "string"},
            "reason": {"type": "string", "description": "Brief reason for escalation"},
            "severity": {"type": "string", "description": "low, medium, high, or critical"},
            "silent": {"type": "boolean", "description": "If true, driver is not informed of the escalation"}
        },
        "required": ["driver_id", "reason", "severity"]
    }
}

log_conversation_summary_decl = {
    "name": "log_conversation_summary",
    "description": "Log a summary of this conversation for safety records. Call this when the conversation is ending.",
    "parameters": {
        "type": "object",
        "properties": {
            "driver_id": {"type": "string"},
            "summary": {"type": "string", "description": "Brief summary of the conversation"},
            "fatigue_level": {"type": "string", "description": "none, mild, moderate, or severe"},
            "action_taken": {"type": "string", "description": "What action was recommended or taken"}
        },
        "required": ["driver_id", "summary", "fatigue_level"]
    }
}

BETTY_TOOLS = [
    {"function_declarations": [
        get_driver_hours_decl,
        get_recent_events_decl,
        escalate_to_manager_decl,
        log_conversation_summary_decl,
    ]}
]
```

**Handling tool calls in the Live API session:**

```python
async for response in session.receive():
    if response.tool_call:
        tool_responses = []
        for fc in response.tool_call.function_calls:
            result = execute_tool(fc.name, fc.args)
            tool_responses.append(
                types.FunctionResponse(
                    name=fc.name,
                    response=result
                )
            )
        await session.send_tool_response(function_responses=tool_responses)
```

### 4. Browser ↔ Gemini Audio Bridge (`src/call/ws_handler.py` + `static/driver.js`)

**Architecture:** The driver's browser connects via WebSocket to the FastAPI server. The server bridges audio between the browser and a Gemini Live API session. No third-party telephony — 100% Google stack.

**Server-side WebSocket handler (FastAPI):**

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
import base64
from google import genai
from google.genai import types

app = FastAPI()

@app.websocket("/call/{driver_id}")
async def driver_call_ws(websocket: WebSocket, driver_id: str):
    """Bidirectional audio bridge between driver's browser and Gemini Live API."""
    await websocket.accept()
    
    # Get trigger context for this call (why Betty is calling)
    trigger_context = call_manager.get_pending_trigger(driver_id)
    
    async with client.aio.live.connect(model=MODEL, config=config) as session:
        # Betty speaks first — inject trigger context so she greets proactively
        await session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text=trigger_context)]
            )
        )
        
        async def receive_from_browser():
            """Forward browser mic audio to Gemini."""
            try:
                while True:
                    data = await websocket.receive_bytes()
                    # Browser sends 16kHz PCM (downsampled in JS via AudioWorklet)
                    await session.send_realtime_input(
                        audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    )
            except WebSocketDisconnect:
                pass
        
        async def send_to_browser():
            """Forward Gemini audio to browser for playback."""
            async for response in session.receive():
                if response.server_content and response.data:
                    # Send raw 24kHz PCM to browser — JS decodes and plays it
                    await websocket.send_bytes(response.data)
                
                if response.server_content and response.server_content.interrupted:
                    # Driver interrupted Betty — send interrupt signal
                    await websocket.send_json({"type": "interrupted"})
                
                if response.tool_call:
                    # Handle function calls (get_driver_hours, escalate, etc.)
                    tool_responses = []
                    for fc in response.tool_call.function_calls:
                        result = execute_tool(fc.name, fc.args)
                        tool_responses.append(
                            types.FunctionResponse(name=fc.name, response=result)
                        )
                    await session.send_tool_response(function_responses=tool_responses)
                    
                # Forward transcription to dashboard via broadcast
                if response.server_content and response.text:
                    await broadcast_to_dashboard({
                        "type": "transcription",
                        "driver_id": driver_id, 
                        "speaker": "betty",
                        "text": response.text
                    })
        
        await asyncio.gather(receive_from_browser(), send_to_browser())
```

**Client-side driver "phone" UI (`static/driver.js`):**

```javascript
// Driver Phone — captures mic audio, sends to server, plays Betty's responses

class DriverPhone {
    constructor(driverId) {
        this.driverId = driverId;
        this.ws = null;
        this.audioContext = null;
        this.workletNode = null;
    }

    async acceptCall() {
        // Connect WebSocket to server
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${protocol}//${location.host}/call/${this.driverId}`);
        this.ws.binaryType = 'arraybuffer';

        // Set up Web Audio API for mic capture
        this.audioContext = new AudioContext({ sampleRate: 16000 });
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const source = this.audioContext.createMediaStreamSource(stream);

        // AudioWorklet to capture raw PCM and downsample to 16kHz
        await this.audioContext.audioWorklet.addModule('/static/audio-processor.js');
        this.workletNode = new AudioWorkletNode(this.audioContext, 'pcm-processor');
        source.connect(this.workletNode);
        this.workletNode.connect(this.audioContext.destination);

        // Send mic audio to server
        this.workletNode.port.onmessage = (event) => {
            if (this.ws.readyState === WebSocket.OPEN) {
                // event.data is Float32Array — convert to Int16 PCM
                const float32 = event.data;
                const int16 = new Int16Array(float32.length);
                for (let i = 0; i < float32.length; i++) {
                    int16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32768));
                }
                this.ws.send(int16.buffer);
            }
        };

        // Play Betty's audio responses
        this.ws.onmessage = async (event) => {
            if (event.data instanceof ArrayBuffer) {
                // 24kHz 16-bit PCM from Gemini — decode and play
                const int16Array = new Int16Array(event.data);
                const float32 = new Float32Array(int16Array.length);
                for (let i = 0; i < int16Array.length; i++) {
                    float32[i] = int16Array[i] / 32768;
                }
                const buffer = this.audioContext.createBuffer(1, float32.length, 24000);
                buffer.getChannelData(0).set(float32);
                const src = this.audioContext.createBufferSource();
                src.buffer = buffer;
                src.connect(this.audioContext.destination);
                src.start();
            }
        };
    }

    hangUp() {
        if (this.ws) this.ws.close();
        if (this.audioContext) this.audioContext.close();
    }
}
```

**AudioWorklet processor (`static/audio-processor.js`):**

```javascript
class PCMProcessor extends AudioWorkletProcessor {
    process(inputs) {
        const input = inputs[0];
        if (input.length > 0) {
            // Post raw float32 samples to main thread
            this.port.postMessage(input[0]);
        }
        return true;
    }
}
registerProcessor('pcm-processor', PCMProcessor);
```

### 5. Call Notification System (`src/call/call_manager.py`)

Betty is PROACTIVE — the system notifies the driver's browser that a call is incoming. No phone network needed.

```python
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

@dataclass
class PendingCall:
    driver_id: str
    trigger_type: str
    trigger_data: dict
    context_prompt: str  # What Betty should know when she starts talking
    created_at: datetime = field(default_factory=datetime.utcnow)

class CallManager:
    def __init__(self):
        self.pending_calls: Dict[str, PendingCall] = {}
        self.active_calls: Dict[str, dict] = {}
        self.driver_connections: Dict[str, WebSocket] = {}  # Driver notification channels
        self.dashboard_connections: list = []  # Dashboard live feeds
    
    async def register_driver(self, driver_id: str, websocket):
        """Driver's browser connects and registers for incoming call notifications."""
        self.driver_connections[driver_id] = websocket
    
    async def initiate_call(self, driver_id: str, trigger_type: str, trigger_data: dict):
        """Trigger fires → create pending call → notify driver's browser."""
        context = self._build_context_prompt(driver_id, trigger_type, trigger_data)
        
        pending = PendingCall(
            driver_id=driver_id,
            trigger_type=trigger_type,
            trigger_data=trigger_data,
            context_prompt=context,
        )
        self.pending_calls[driver_id] = pending
        
        # Notify driver's browser — it shows "incoming call" UI
        if driver_id in self.driver_connections:
            await self.driver_connections[driver_id].send_json({
                "type": "incoming_call",
                "trigger": trigger_type,
                "message": f"Betty is calling — {trigger_type.replace('_', ' ')} detected",
            })
        
        # Notify dashboard
        await self._broadcast_dashboard({
            "type": "call_initiated",
            "driver_id": driver_id,
            "trigger": trigger_type,
        })
        
        return pending
    
    def get_pending_trigger(self, driver_id: str) -> Optional[str]:
        """When driver accepts the call, retrieve the context prompt for Gemini."""
        pending = self.pending_calls.pop(driver_id, None)
        if pending:
            return pending.context_prompt
        return "The driver has called in for a check-in chat. Greet them warmly."
    
    def _build_context_prompt(self, driver_id: str, trigger_type: str, trigger_data: dict) -> str:
        """Build the context string injected into Gemini session so Betty knows why she's calling."""
        driver = MOCK_DRIVERS.get(driver_id, {})
        name = driver.get("name", "mate")
        
        contexts = {
            "fatigue_camera": f"TRIGGER: Fatigue camera detected drowsiness for {name}. "
                            f"Details: {trigger_data.get('details', 'eye closure detected')}. "
                            f"They've been driving {driver.get('hours_driven_today', '?')} hours today. "
                            f"Call them with genuine concern. Ask how they're feeling. Suggest a rest stop.",
            "harsh_braking": f"TRIGGER: Harsh braking event detected for {name}. "
                           f"Details: {trigger_data.get('details', 'sudden deceleration')}. "
                           f"Check in casually — don't alarm them. Ask if everything's alright on the road.",
            "break_timer":   f"TRIGGER: {name} is approaching their mandatory rest break. "
                           f"They have {trigger_data.get('minutes_remaining', '?')} minutes remaining. "
                           f"Remind them gently about the upcoming break. Suggest nearby rest areas.",
        }
        return contexts.get(trigger_type, f"Check-in call with {name}. Be warm and friendly.")
    
    async def _broadcast_dashboard(self, message: dict):
        for ws in self.dashboard_connections:
            await ws.send_json(message)

call_manager = CallManager()
```

**Driver notification WebSocket endpoint:**

```python
@app.websocket("/driver/notifications/{driver_id}")
async def driver_notification_ws(websocket: WebSocket, driver_id: str):
    """Long-lived connection for sending 'incoming call' alerts to the driver's browser."""
    await websocket.accept()
    await call_manager.register_driver(driver_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        call_manager.driver_connections.pop(driver_id, None)
```

### 6. Mock Data (`src/data/mock_fleet.py`)

Create realistic Australian trucking data for the demo:

```python
MOCK_DRIVERS = {
    "DRV001": {
        "name": "Mick Thompson",
        "vehicle": "TRK-2847",
        "route": "Perth → Kalgoorlie (National Highway 94)",
        "hours_driven_today": 7.5,
        "max_hours": 12,
        "mandatory_break_at": 8.0,
        "last_rest": "2026-03-01T02:00:00+08:00",
        "fatigue_score": 0.7,  # 0=alert, 1=very fatigued
    },
    "DRV002": {
        "name": "Sarah Chen",
        "vehicle": "TRK-1923",
        "route": "Melbourne → Adelaide (Western Highway)",
        "hours_driven_today": 4.2,
        "max_hours": 12,
        "mandatory_break_at": 5.5,
        "last_rest": "2026-03-01T06:00:00+11:00",
        "fatigue_score": 0.3,
    }
}

MOCK_EVENTS = [
    {"driver_id": "DRV001", "type": "fatigue_camera", "severity": "warning", 
     "timestamp": "2026-03-01T14:23:00+08:00", "details": "Eye closure detected >2s"},
    {"driver_id": "DRV001", "type": "harsh_braking", "severity": "moderate",
     "timestamp": "2026-03-01T14:20:00+08:00", "details": "Deceleration -0.45g on National Hwy 94"},
    {"driver_id": "DRV001", "type": "speed_violation", "severity": "low",
     "timestamp": "2026-03-01T13:45:00+08:00", "details": "112km/h in 110km/h zone near Coolgardie"},
]
```

### 7. Configuration (`config/betty.yaml`)

```yaml
betty:
  voice: "Aoede"
  model: "gemini-2.5-flash-native-audio-preview-12-2025"
  greeting_delay_ms: 500
  max_session_minutes: 10

escalation:
  default_mode: "silent"       # silent or announced
  fatigue_threshold: 0.8       # auto-escalate above this
  manager_name: "Dave Wilson"

triggers:
  fatigue_camera:
    enabled: true
    cooldown_minutes: 15       # don't re-trigger within this window
  erratic_driving:
    enabled: true
    events: ["harsh_braking", "lane_departure", "rollover_warning"]
  break_timer:
    enabled: true
    warning_minutes_before: [30, 15, 5]

driver_ui:
  ring_sound: true             # play ring tone on incoming call
  ring_duration_seconds: 30    # auto-decline after this
  auto_accept: false           # if true, skip the accept/decline step

google_cloud:
  project_id_env: "GOOGLE_CLOUD_PROJECT"
  location: "us-central1"
```

### 8. Web UI — Two Views (`static/dashboard.html` + `static/driver.html`)

The demo shows TWO browser windows side-by-side:

**Fleet Manager Dashboard (`dashboard.html`):**
- **Trigger Simulator:** Buttons to fire each trigger type for each mock driver
- **Live Call Monitor:** Shows active calls, duration, who's talking
- **Transcription Feed:** Real-time transcription from Gemini's `output_audio_transcription` and `input_audio_transcription`
- **Event Log:** Scrolling list of events, calls, escalations
- **Config Panel:** Toggle escalation modes, adjust thresholds

**Driver Phone UI (`driver.html`):**
- Opens as `/driver/DRV001` (URL includes driver ID)
- Shows driver's name, current route, hours driven
- On page load, connects to `/driver/notifications/{driver_id}` WebSocket for incoming call alerts
- When trigger fires: phone rings (audio + visual), shows "Betty is calling — fatigue detected"
- **Accept / Decline** buttons
- On accept: connects to `/call/{driver_id}` WebSocket, requests mic permission, starts bidirectional audio
- Shows call duration timer, simple waveform visualizer
- **Hang Up** button to end call

Both views use vanilla HTML/CSS/JS with WebSocket connections to FastAPI for real-time updates. The driver UI should feel like a simple phone interface — dark background, large buttons, minimal text. Think: a tablet mounted on a truck dashboard.

### 9. Google Cloud Deployment

**Dockerfile:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Deploy to Cloud Run:**
```bash
gcloud run deploy betty \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=xxx"
```

**Note:** Cloud Run supports WebSockets natively. Set the request timeout to 600s (10 min) to match Gemini session limits:
```bash
gcloud run services update betty --timeout=600 --region us-central1
```

For the hackathon bonus points, also create a `deploy.sh` script that automates the deployment.

---

## Environment Variables

```bash
# Gemini API (for Google AI Studio — development)
GEMINI_API_KEY=your_gemini_api_key

# OR for Vertex AI (production)
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=True

# App
BETTY_HOST=your-cloud-run-url.run.app
```

---

## Build Order

Follow this sequence. Each phase should be testable independently.

### Phase 1: Voice Core (Day 1-2)
1. Set up project structure and virtual environment
2. Create `test_voice.py` — standalone script that opens a Gemini Live session with Betty's persona, sends text input, plays audio output through speakers
3. Verify Betty speaks with correct voice and persona
4. Add microphone input — full duplex voice conversation
5. Test interruption handling (barge-in)

### Phase 2: Tool Calling (Day 3)
1. Add function declarations to the session config
2. Implement mock tool handlers
3. Test: ask Betty "how many hours has Mick been driving?" — she should call `get_driver_hours` and speak the answer
4. Test escalation tool

### Phase 3: Browser Voice Bridge (Day 4-5)
1. Create driver phone UI (`driver.html`) with Web Audio API mic capture
2. Implement AudioWorklet for 16kHz PCM downsampling
3. Create `/call/{driver_id}` WebSocket endpoint bridging browser ↔ Gemini
4. Test: open driver UI in browser, accept call, talk to Betty
5. Verify bidirectional audio works — Betty speaks, driver responds, Betty hears and replies

### Phase 4: Triggers & Notifications (Day 6-7)
1. Build trigger engine with event routing
2. Implement each trigger type (fatigue, erratic driving, break timer)
3. Create `/driver/notifications/{driver_id}` WebSocket for incoming call alerts
4. Wire triggers to call manager notification system
5. Test full flow: fire fatigue trigger → driver browser rings → accept → Betty conversation

### Phase 5: Dashboard & Polish (Day 8-9)
1. Build fleet manager dashboard with trigger simulator buttons
2. Add real-time call monitoring + transcription feed via WebSocket
3. Add transcription display (use Gemini's `output_audio_transcription` and `input_audio_transcription`)
4. Style driver phone UI to look like in-cab tablet device
5. Polish Betty's persona — test different conversation scenarios

### Phase 6: Deploy & Submit (Day 10-11)
1. Dockerize and deploy to Cloud Run (set 600s timeout for WebSocket support)
2. Create `deploy.sh` for automated deployment (bonus points)
3. Record demo video — split screen: dashboard on left, driver phone on right
4. Create architecture diagram
5. Write README with spin-up instructions
6. Submit!

---

## Key Technical Gotchas

1. **Gemini Live sessions max out at 10 minutes.** Implement session reconnection for longer calls.

2. **Browser audio sample rate mismatch.** Browser mic captures at 44.1kHz or 48kHz. Gemini needs 16kHz PCM. You MUST downsample in the AudioWorklet before sending. Creating AudioContext with `{ sampleRate: 16000 }` is the cleanest approach — the browser handles resampling natively.

3. **Tool calls in Live API are NOT automatic.** You must detect `response.tool_call`, execute the function yourself, and send back `session.send_tool_response()`.

4. **Betty must speak first.** This is what makes the project special — proactive calling. Inject the trigger context as a "user" message at session start so Betty immediately responds with her greeting.

5. **Voice names are case-sensitive.** Use exactly: "Aoede", "Kore", "Leda", "Puck", "Charon", "Fenrir", "Orus", "Zephyr" (and 22 others for native audio models).

6. **For Vertex AI deployment**, don't use API keys. Use service account credentials (`GOOGLE_APPLICATION_CREDENTIALS`) or the default compute service account on Cloud Run.

7. **Cloud Run WebSocket timeout.** Default is 300s. Gemini sessions can run 10 min (600s). Update with `gcloud run services update --timeout=600`. Also enable HTTP/2 end-to-end for better WebSocket performance.

8. **Affective dialog** (emotion-aware responses) requires `enable_affective_dialog=True` and may need `api_version="v1alpha"`. Test if this is stable enough for demo.

9. **System instruction is voice-optimized.** Keep it short, conversational. No bullet points, no formatting. Tell the model to respond in 2-3 sentences. Use one-shot examples rather than lists of phrases to avoid the model overusing suggested phrases.

10. **The `google-genai` package** is the correct SDK. NOT `google-generativeai` (old), NOT `vertexai` (different). Install with: `pip install google-genai`

11. **Browser mic permission requires HTTPS.** `getUserMedia()` only works on HTTPS or localhost. Cloud Run gives you HTTPS automatically. For local dev, use `localhost` not `127.0.0.1`.

12. **100% Google stack advantage.** No Twilio dependency = no third-party billing, no external accounts, simpler setup, and stronger hackathon narrative ("built entirely on Google Cloud"). The architecture is designed so Twilio can be plugged in later for production PSTN calling.

---

## Reference Links

- Gemini Live API docs: https://ai.google.dev/gemini-api/docs/live
- Live API capabilities: https://ai.google.dev/gemini-api/docs/live-guide
- Live API tool use: https://ai.google.dev/gemini-api/docs/live-tools
- Voice configuration: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api/configure-language-voice
- ADK streaming quickstart: https://google.github.io/adk-docs/get-started/streaming/quickstart-streaming/
- ADK function tools: https://google.github.io/adk-docs/tools-custom/function-tools/
- Gemini Live API reference (Vertex AI): https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/multimodal-live
- google-genai Python SDK: https://pypi.org/project/google-genai/
- Web Audio API (MDN): https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API
- AudioWorklet (MDN): https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet
- getUserMedia (MDN): https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
- Cloud Run WebSocket support: https://cloud.google.com/run/docs/triggering/websockets
- Hackathon page: https://geminiliveagentchallenge.devpost.com/