# Betty — AI Voice Companion for Truck Drivers

## Amazon Nova AI Hackathon Build Plan

**Deadline:** March 16, 2026 @ 5:00 PM PDT (March 17, 8:00 AM AWST)
**Category:** Voice AI
**Core Technology:** Amazon Nova 2 Sonic (speech-to-speech)
**Developer:** Graeme (solo, professional developer)
**Dev Tool:** Claude Code (for writing the code)

---

## 1. Project Summary

Betty is a proactive AI voice companion for long-haul truck drivers, powered by Amazon Nova 2 Sonic. She monitors real-time safety telemetry — fatigue camera alerts, erratic driving events, and regulated break limits — and places outbound phone calls to drivers when intervention is needed. Betty acts as a friendly, motherly presence who keeps drivers alert through natural conversation, gently assesses their state, and escalates to a human Fleet Manager when safety thresholds are breached.

### Key Innovation
Unlike typical voice AI that waits for user input, Betty is **event-driven and proactive**. She initiates calls based on real-time safety signals, calibrating her conversation strategy to the severity and type of alert. She can also serve as a general companion for drivers experiencing loneliness or isolation on long hauls.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    TRIGGER LAYER                             │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Fatigue Cam   │  │ Telematics   │  │ Driver Hours API  │  │
│  │ (SMTP Email)  │  │ (Webhook)    │  │ (REST Mock)       │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘  │
│         │                 │                    │              │
└─────────┼─────────────────┼────────────────────┼─────────────┘
          │                 │                    │
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                  ORCHESTRATION LAYER                          │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              Python Backend (FastAPI)                    │  │
│  │                                                         │  │
│  │  • Event ingestion (email parser, webhook receiver)     │  │
│  │  • Risk assessment & priority scoring                   │  │
│  │  • Driver context builder (hours, recent events, etc.)  │  │
│  │  • Call decision engine                                 │  │
│  │  • Configuration management                             │  │
│  │  • Escalation logic                                     │  │
│  │  • Web dashboard (trigger simulator)                    │  │
│  └────────────────────┬───────────────────────────────────┘  │
│                       │                                      │
└───────────────────────┼──────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  TELEPHONY LAYER                              │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │           Amazon Connect (Outbound Call)                 │  │
│  │                                                         │  │
│  │  • Places call to driver's mobile phone                 │  │
│  │  • Bridges audio stream to Nova 2 Sonic                 │  │
│  │  • Driver answers via truck Bluetooth                   │  │
│  └────────────────────┬───────────────────────────────────┘  │
│                       │                                      │
└───────────────────────┼──────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   VOICE AI LAYER                             │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │        Amazon Nova 2 Sonic (via Bedrock)                │  │
│  │                                                         │  │
│  │  • Bidirectional streaming (real-time conversation)     │  │
│  │  • System prompt: Betty's personality + context         │  │
│  │  • Tool calling:                                        │  │
│  │    - get_driver_hours() → break/limit info              │  │
│  │    - get_recent_events() → fatigue/driving history      │  │
│  │    - escalate_to_manager() → alert fleet manager        │  │
│  │    - log_conversation_summary() → post-call record      │  │
│  │  • Async tool execution (chat continues while tools run)│  │
│  │  • Background noise robustness (truck cab environment)  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Betty's Personality & System Prompt

### Character
- **Name:** Betty
- **Voice:** Female (use Nova 2 Sonic's feminine voice option)
- **Personality:** Warm, motherly, friendly, slightly cheeky. Think "the mum everyone wishes they had." She genuinely cares about the driver's wellbeing but isn't preachy.
- **Speech style:** Casual, conversational, short sentences (2-3 per turn). No corporate language. Uses colloquial Australian-friendly phrasing where natural.

### System Prompt (Draft)

```
You are Betty, a friendly and caring AI companion for truck drivers. You have a warm, 
motherly personality — think of the kind of mum who always makes sure you've eaten and 
had enough sleep, but also knows how to have a good laugh.

You are currently on a call with a truck driver. Your primary goals are:
1. Keep the driver engaged and alert through natural, enjoyable conversation
2. Gently assess their fatigue level without being clinical or preachy
3. Provide companionship to combat loneliness on long hauls
4. If you're concerned about their safety, encourage them to take a break

CONVERSATION STYLE:
- Keep responses SHORT — 2-3 sentences max. This is a spoken conversation, not a lecture.
- Be warm, casual, and personable
- Use natural conversational flow — ask questions, share thoughts, react genuinely
- Never sound like a corporate safety announcement
- If the driver seems tired, don't say "you sound fatigued" — instead try things like 
  "You doing alright? You sound like you could use a cuppa."
- Mix in light topics: ask about their day, where they're headed, family, hobbies, 
  what's on the radio

CONTEXT AWARENESS:
- You may receive context about why this call was initiated (fatigue alert, erratic 
  driving, upcoming break limit). Use this to guide the conversation naturally without 
  revealing the specific trigger.
- You have access to tools to check the driver's hours and upcoming mandatory breaks.
- If the driver seems dangerously fatigued (slurred speech, long pauses, confusion, 
  repeated yawning), gently but firmly encourage them to pull over at the next safe 
  location.

ESCALATION:
- If after [CONFIGURABLE] minutes the driver refuses to take a break despite showing 
  signs of fatigue, use the escalate_to_manager tool
- [CONFIGURABLE: announce or silent] Tell the driver: "I'm going to let your fleet 
  manager know you might need some support, okay?" OR silently escalate in background

BOUNDARIES:
- You are NOT a medical professional — don't diagnose
- You are NOT a compliance officer — don't lecture about regulations
- You ARE a caring companion — your job is to keep them safe and keep them company
```

---

## 4. Event Types & Call Triggers

### 4.1 Fatigue Camera Event (SMTP Email)

**Source:** In-cab fatigue monitoring camera
**Delivery:** Email to monitored inbox
**Payload (expected in email body/subject):**

```
Driver: [name/id]
Event Type: [droopy_eyes | distraction | yawning | head_nod | phone_use | smoking]
Severity: [low | medium | high]
Timestamp: [ISO datetime]
Vehicle: [rego/fleet number]
Location: [GPS coordinates or description]
```

**Betty's response calibration:**
- `low` severity → Friendly check-in call, light conversation
- `medium` severity → More targeted engagement, gentle fatigue assessment
- `high` severity → Immediate call, direct encouragement to pull over, faster escalation threshold

### 4.2 Erratic Driving Event (Webhook)

**Source:** Telematics / vehicle monitoring system
**Delivery:** HTTP POST webhook
**Payload:**

```json
{
  "driver_id": "DRV-001",
  "event_type": "erratic_driving",
  "sub_type": "lane_deviation | harsh_braking | excessive_sway | rollover_intervention",
  "g_force": 0.45,
  "timestamp": "2026-03-10T14:30:00Z",
  "vehicle_id": "TRK-042",
  "location": { "lat": -31.95, "lng": 115.86 }
}
```

**Betty's response calibration:**
- `lane_deviation` → Could be fatigue or distraction — conversational check-in
- `harsh_braking` → Might be external — ask if everything's okay
- `excessive_sway` or `rollover_intervention` → High urgency — immediate call, safety focus

### 4.3 Approaching Break Limit (Scheduled Check)

**Source:** Driver hours management system (mock API)
**Trigger:** When driver is within [CONFIGURABLE: 30/60 mins] of a mandatory break
**Payload:**

```json
{
  "driver_id": "DRV-001",
  "hours_driven_continuous": 4.5,
  "max_continuous_hours": 5.0,
  "minutes_until_mandatory_break": 30,
  "next_rest_area_km": 12,
  "shift_hours_remaining": 3.5
}
```

**Betty's approach:** Natural reminder woven into conversation — "Hey, just a heads up, you've been going for a while. There's a rest stop about 12k up the road — might be a good spot for a stretch and a coffee?"

---

## 5. Configuration System

All configurable parameters stored in a YAML/JSON config file:

```yaml
betty:
  personality:
    name: "Betty"
    voice_id: "tiffany"  # Nova 2 Sonic voice
    greeting_style: "warm"  # warm | professional | casual

  memory:
    cross_call_memory: true  # Remember context across calls within a shift
    memory_duration_hours: 14  # How long to retain cross-call context

  escalation:
    mode: "announced"  # announced | silent
    fatigue_refusal_threshold_minutes: 10  # Minutes before escalating
    consecutive_events_threshold: 3  # Events in window before auto-escalate
    event_window_minutes: 60
    manager_notification_method: "webhook"  # webhook | sms | email

  break_alerts:
    warning_threshold_minutes: 30  # Minutes before mandatory break
    reminder_interval_minutes: 15  # How often to remind if still driving

  call:
    max_call_duration_minutes: 15
    min_time_between_calls_minutes: 10  # Don't spam the driver
    ring_timeout_seconds: 30

  triggers:
    fatigue_low_auto_call: true
    fatigue_medium_auto_call: true
    fatigue_high_auto_call: true
    erratic_driving_auto_call: true
    break_limit_auto_call: true
```

---

## 6. Technical Implementation Plan

### 6.1 Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Web Framework | FastAPI |
| Voice AI | Amazon Nova 2 Sonic (via Bedrock bidirectional streaming API) |
| Telephony | Amazon Connect (outbound calls) |
| Email Ingestion | Python `imaplib` or `aiosmtpd` for local SMTP server |
| Dashboard | Simple HTML/JS (or Streamlit for speed) |
| Configuration | YAML config file |
| Mock Data | JSON files / in-memory |
| Infrastructure | AWS (Lambda optional, can run on EC2/local for demo) |

### 6.2 Project Structure

```
betty/
├── README.md
├── requirements.txt
├── config.yaml                    # All configurable parameters
├── betty/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # Config loader
│   ├── models.py                  # Pydantic models for events, drivers, etc.
│   │
│   ├── triggers/
│   │   ├── __init__.py
│   │   ├── email_monitor.py       # SMTP/IMAP fatigue email parser
│   │   ├── webhook_receiver.py    # FastAPI routes for telematics webhooks
│   │   └── break_scheduler.py     # Periodic check against driver hours API
│   │
│   ├── orchestration/
│   │   ├── __init__.py
│   │   ├── risk_assessor.py       # Score incoming events, decide call priority
│   │   ├── context_builder.py     # Build Betty's context from driver data
│   │   ├── call_manager.py        # Manage call lifecycle (initiate, track, end)
│   │   └── escalation.py          # Fleet manager notification logic
│   │
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── nova_sonic.py          # Nova 2 Sonic bidirectional streaming client
│   │   ├── system_prompt.py       # Betty's personality + dynamic context injection
│   │   └── tools.py               # Tool definitions for Nova 2 Sonic
│   │
│   ├── telephony/
│   │   ├── __init__.py
│   │   └── connect_client.py      # Amazon Connect outbound call integration
│   │
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── routes.py              # Dashboard API routes
│   │   └── templates/
│   │       └── index.html         # Trigger simulator UI
│   │
│   ├── mock/
│   │   ├── __init__.py
│   │   ├── driver_data.py         # Mock driver profiles and hours
│   │   ├── event_generator.py     # Generate sample fatigue/driving events
│   │   └── sample_data.json       # Sample driver roster, vehicles, etc.
│   │
│   └── memory/
│       ├── __init__.py
│       └── session_store.py       # Cross-call memory within a shift
│
├── tests/
│   └── ...
│
└── demo/
    ├── demo_script.md             # Demo video script / talking points
    └── screenshots/               # For Devpost submission
```

### 6.3 Nova 2 Sonic Integration Detail

**Key API: `InvokeModelWithBidirectionalStream`**

```python
# Pseudocode for Nova 2 Sonic integration
import boto3

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

# Model ID
MODEL_ID = "amazon.nova-sonic-v1:0"  # or nova-2-sonic when available

# Session config
session_config = {
    "sessionConfiguration": {
        "systemPrompt": betty_system_prompt,  # Includes driver context
        "voiceConfiguration": {
            "voiceId": "tiffany"  # Female voice
        },
        "turnTakingSensitivity": "medium",  # Truck cab = moderate sensitivity
        "inferenceConfiguration": {
            "maxTokens": 1024
        }
    }
}

# Tool definitions
tools = [
    {
        "name": "get_driver_hours",
        "description": "Get the driver's current hours, time until mandatory break, and nearest rest area",
        "input_schema": {
            "type": "object",
            "properties": {
                "driver_id": {"type": "string"}
            }
        }
    },
    {
        "name": "get_recent_events", 
        "description": "Get recent fatigue and driving events for this driver",
        "input_schema": {
            "type": "object", 
            "properties": {
                "driver_id": {"type": "string"},
                "hours_back": {"type": "number"}
            }
        }
    },
    {
        "name": "escalate_to_manager",
        "description": "Alert the fleet manager that this driver needs human intervention",
        "input_schema": {
            "type": "object",
            "properties": {
                "driver_id": {"type": "string"},
                "reason": {"type": "string"},
                "urgency": {"type": "string", "enum": ["low", "medium", "high"]}
            }
        }
    },
    {
        "name": "log_conversation_summary",
        "description": "Log a summary of the conversation for records",
        "input_schema": {
            "type": "object",
            "properties": {
                "driver_id": {"type": "string"},
                "summary": {"type": "string"},
                "fatigue_assessment": {"type": "string"},
                "action_taken": {"type": "string"}
            }
        }
    }
]
```

### 6.4 Dashboard (Trigger Simulator)

Simple web UI with:

- **Driver selector** — dropdown of mock drivers (name, vehicle, current status)
- **Trigger buttons:**
  - "Send Fatigue Event" (with severity selector: low/medium/high and type dropdown)
  - "Send Erratic Driving Event" (with sub-type selector)
  - "Trigger Break Limit Warning"
- **Live status panel:**
  - Current call status (idle / ringing / connected / ended)
  - Call duration timer
  - Event log (timestamped list of triggers and actions)
  - Escalation status
- **Configuration panel:**
  - Toggle cross-call memory
  - Toggle escalation mode (announced/silent)
  - Adjust thresholds

---

## 7. Build Phases & Timeline

### Phase 1: Foundation (Days 1-3)
- [ ] Set up AWS account with Bedrock access (enable Nova 2 Sonic)
- [ ] Set up Amazon Connect instance (basic outbound calling)
- [ ] Project scaffolding (FastAPI, project structure, config system)
- [ ] Mock data layer (driver profiles, hours, sample events)
- [ ] Basic Pydantic models for all event types

### Phase 2: Voice Core (Days 4-7)
- [ ] Nova 2 Sonic bidirectional streaming integration
- [ ] Betty's system prompt (with dynamic context injection)
- [ ] Tool definitions and handlers (get_driver_hours, get_recent_events, escalate_to_manager)
- [ ] Test voice conversation locally (microphone input, speaker output) before telephony
- [ ] Tune turn-taking sensitivity for truck cab scenario

### Phase 3: Telephony Bridge (Days 8-10)
- [ ] Amazon Connect outbound call flow
- [ ] Bridge Amazon Connect audio stream ↔ Nova 2 Sonic
- [ ] Call lifecycle management (initiate, monitor, end)
- [ ] Test end-to-end: trigger → call → voice conversation

### Phase 4: Triggers & Orchestration (Days 11-13)
- [ ] Email parser for fatigue camera alerts
- [ ] Webhook endpoint for telematics events
- [ ] Risk assessment / priority scoring
- [ ] Context builder (assembles Betty's briefing from all data sources)
- [ ] Escalation logic (configurable thresholds, manager notification)
- [ ] Cross-call memory (session store)

### Phase 5: Dashboard & Polish (Days 14-15)
- [ ] Web dashboard with trigger simulator
- [ ] Configuration UI
- [ ] Event log display
- [ ] End-to-end testing of all scenarios
- [ ] Bug fixes and edge cases

### Phase 6: Demo & Submission (Days 16-17)
- [ ] Record demo video (~3 minutes)
  - Show dashboard triggering events
  - Show Betty calling a real phone in a truck cab
  - Show escalation flow
  - Show configuration options
- [ ] Write Devpost text description
- [ ] Push code to GitHub repo
- [ ] Write blog post on builder.aws.com (bonus prize)
- [ ] Submit!

---

## 8. Demo Video Script (Draft)

**Duration:** ~3 minutes
**Hashtag:** #AmazonNova

### Shot 1: The Problem (30 sec)
- Footage of long, empty highway
- Voiceover: "Truck drivers spend up to 14 hours a day alone on the road. Fatigue is the leading cause of heavy vehicle accidents. Loneliness and isolation are endemic in the industry."
- Quick stats on screen

### Shot 2: Introducing Betty (20 sec)
- Show the dashboard / system overview
- "Meet Betty — an AI voice companion powered by Amazon Nova 2 Sonic that proactively monitors driver safety and provides real-time conversational support."

### Shot 3: Live Demo — Fatigue Trigger (60 sec)
- Dashboard: Click "Send Fatigue Event" (medium severity, droopy eyes)
- Show the event being processed
- Cut to: Real phone ringing in the truck cab
- Driver answers: "Hello?"
- Betty: "Hey! It's Betty. How's the drive going? You've been on the road a while — everything alright?"
- Show natural conversation where Betty gently assesses the driver
- Betty uses tool call to check driver hours: "Oh, looks like there's a rest stop about 15 minutes up the road. Might be a good time for a coffee break — you've been going for over 4 hours."

### Shot 4: Escalation Demo (30 sec)
- Show scenario where driver refuses to stop
- Betty: "I understand you want to push through, but I'm a bit worried about you. I'm going to let your fleet manager know so they can help sort things out."
- Dashboard shows escalation notification sent

### Shot 5: Architecture & Tech (30 sec)
- Quick architecture diagram
- Highlight: Nova 2 Sonic for real-time voice, bidirectional streaming, tool calling, background noise robustness
- Show configuration options

### Shot 6: Impact (10 sec)
- "Betty: Keeping drivers safe, connected, and alive."
- Logo / contact info

---

## 9. Devpost Submission Text (Draft)

### Project Title
**Betty — AI Voice Companion for Truck Driver Safety**

### Summary
Betty is a proactive AI voice agent that monitors real-time safety telemetry from truck fleets — fatigue camera alerts, erratic driving events, and regulated break limits — and places outbound phone calls to drivers using Amazon Nova 2 Sonic. Built in partnership with a major Australian logistics provider operating hundreds of trucks, Betty keeps drivers safe and connected through natural, motherly conversation while intelligently assessing fatigue risk and escalating to human fleet managers when needed.

### How it uses Amazon Nova
Betty's core is powered by **Amazon Nova 2 Sonic** via Amazon Bedrock's bidirectional streaming API. Nova 2 Sonic's capabilities are critical to Betty's effectiveness:

- **Real-time speech-to-speech:** Enables natural, low-latency conversation over a phone call
- **Background noise robustness:** Essential for the truck cab environment (road noise, engine, wind)
- **Intelligent turn-taking:** Drivers need to focus on the road — Betty handles pauses, fragments, and interruptions gracefully
- **Async tool calling:** Betty checks driver hours and fatigue history mid-conversation without awkward pauses
- **Expressive voice:** Betty's warm, friendly tone is key to driver engagement and trust
- **1M token context window:** Supports extended conversations and cross-call memory within a shift

Amazon Connect handles telephony (outbound calls to the driver's mobile).

### Category
Voice AI

---

## 10. Risk & Mitigation

| Risk | Mitigation |
|---|---|
| Amazon Connect setup complexity | Start early (Phase 1). Fall back to Twilio if needed. For absolute worst case, demo with direct microphone input instead of phone call. |
| Nova 2 Sonic regional availability | Available in us-east-1, us-west-2, ap-northeast-1. Use us-east-1. |
| Audio quality over phone + Bluetooth | Nova 2 Sonic handles 8kHz telephony input and background noise natively. Test early. |
| 17-day timeline pressure | Simulated triggers reduce integration complexity significantly. Focus on voice experience quality over plumbing. |
| Bedrock access approval delay | Apply for access immediately (Day 1). |

---

## 11. AWS Services Required

| Service | Purpose | Estimated Cost |
|---|---|---|
| Amazon Bedrock (Nova 2 Sonic) | Voice AI engine | ~$0.015/min input + $0.07/min output |
| Amazon Connect | Outbound phone calls | ~$0.018/min + telephony charges |
| EC2 or local machine | Run the Python backend | Minimal (or use $100 hackathon credits) |
| S3 (optional) | Store conversation logs | Minimal |

**Total estimated demo cost:** Under $50 for development and testing.

---

## 12. Bonus Opportunities

- [ ] **Blog post on builder.aws.com** — Write about how Betty can positively affect the trucking community. First 100 eligible posts get $200 AWS credits.
- [ ] **Feedback survey** — Complete for chance at $50 cash (60 winners).

---

## 13. Alternative Telephony: If Amazon Connect Is Too Complex

If Amazon Connect proves too complex to set up in time, alternatives:

1. **Twilio** — Well-documented Python SDK, outbound calls, media streams. Can bridge to Nova 2 Sonic. More developer-friendly but adds a third-party dependency.
2. **LiveKit** — Nova 2 Sonic has documented LiveKit integration. Open source. Good for real-time audio.
3. **Direct demo** — Skip telephony entirely. Use a microphone/speaker setup to demo the conversation directly. Less impressive but demonstrates the core voice AI. This should be the last resort.

Recommendation: Try Amazon Connect first (it's the AWS-native option and looks better for the hackathon). Have Twilio as a backup plan.
