"""FastAPI application — Betty voice companion server.

Mounts static files, registers WebSocket endpoints, health check, trigger API.
"""

import asyncio
import base64
import logging
import os

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import markdown
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from src.call.call_manager import CallManager
from src.call.ws_handler import handle_driver_call

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Betty — AI Voice Companion", version="2.0.0")

# Shared state
call_manager = CallManager()
event_log: list[dict] = []

# Mount static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
SFX_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "sfx")
app.mount("/sfx", StaticFiles(directory=SFX_DIR), name="sfx")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- Config ---

def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "betty.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# --- Health check ---

@app.get("/health")
async def health():
    return {"status": "ok", "service": "betty"}


# --- Trigger API ---

class TriggerRequest(BaseModel):
    driver_id: str
    trigger_type: str  # fatigue_camera | erratic_driving | break_limit | companion_check_in
    severity: Optional[str] = None
    fatigue_event_type: Optional[str] = None
    erratic_sub_type: Optional[str] = None
    g_force: Optional[float] = None
    simulate: bool = False
    persona_mood: Optional[str] = None
    persona_situation: Optional[str] = None
    persona_resistance: Optional[str] = None


@app.post("/api/triggers/trigger")
async def trigger_event(req: TriggerRequest):
    """Receive a trigger event and initiate a call to the driver."""
    from src.data.mock_fleet import get_driver, add_event
    from datetime import datetime, timezone

    driver = get_driver(req.driver_id)
    if not driver:
        return JSONResponse(status_code=404, content={"error": f"Unknown driver: {req.driver_id}"})

    trigger_data = {
        "severity": req.severity,
        "fatigue_event_type": req.fatigue_event_type,
        "erratic_sub_type": req.erratic_sub_type,
        "g_force": req.g_force,
    }

    # Log the event
    event_entry = {
        "type": req.trigger_type,
        **trigger_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    add_event(req.driver_id, event_entry)

    # Add to event log for dashboard
    event_log.append({
        "type": "trigger",
        "message": f"{req.trigger_type} for {driver['first_name']} {driver['last_name']}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    if req.simulate:
        # Launch simulated call in background
        from src.call.simulated_call import run_simulated_call
        persona = {}
        if req.persona_mood:
            persona["mood"] = req.persona_mood
        if req.persona_situation:
            persona["situation"] = req.persona_situation
        if req.persona_resistance:
            persona["resistance"] = req.persona_resistance
        asyncio.create_task(run_simulated_call(
            driver_id=req.driver_id,
            trigger_type=req.trigger_type,
            trigger_data=trigger_data,
            call_manager=call_manager,
            persona=persona if persona else None,
        ))
        return {
            "status": "simulation_started",
            "driver_id": req.driver_id,
            "trigger_type": req.trigger_type,
        }

    # Normal flow: risk assessment + driver notification
    from src.triggers.trigger_engine import assess_and_call
    result = await assess_and_call(
        call_manager=call_manager,
        driver_id=req.driver_id,
        trigger_type=req.trigger_type,
        trigger_data=trigger_data,
        event_log=event_log,
    )

    return result


# --- Driver-initiated call ---

@app.post("/api/call/driver-initiate/{driver_id}")
async def driver_initiate_call(driver_id: str, simulate: bool = False):
    """Driver initiates a call to Betty."""
    from src.data.mock_fleet import get_driver

    driver = get_driver(driver_id)
    if not driver:
        return JSONResponse(status_code=404, content={"error": f"Unknown driver: {driver_id}"})

    trigger_data = {}

    if simulate:
        from src.call.simulated_call import run_simulated_call
        asyncio.create_task(run_simulated_call(
            driver_id=driver_id,
            trigger_type="driver_initiated",
            trigger_data=trigger_data,
            call_manager=call_manager,
        ))
        return {"status": "simulation_started", "driver_id": driver_id}

    # Real call: create pending call so ws_handler can pick it up
    call_manager.initiate_call(driver_id, "driver_initiated", trigger_data)
    return {"status": "call_ready", "driver_id": driver_id}


# --- Call WebSocket (driver voice connection) ---

@app.websocket("/call/{driver_id}")
async def call_websocket(ws: WebSocket, driver_id: str):
    """WebSocket endpoint for driver voice call."""
    await handle_driver_call(ws, driver_id, call_manager)


# --- Driver Notification WebSocket ---

@app.websocket("/driver/notifications/{driver_id}")
async def driver_notifications(ws: WebSocket, driver_id: str):
    """WebSocket for sending call notifications to driver's browser."""
    await ws.accept()
    call_manager.register_notification_socket(driver_id, ws)
    try:
        # Keep connection alive, handle pings
        while True:
            data = await ws.receive_text()
            # Client may send pings or other messages
    except WebSocketDisconnect:
        pass
    finally:
        call_manager.unregister_notification_socket(driver_id)


# --- Dashboard WebSocket ---

@app.websocket("/dashboard/ws")
async def dashboard_websocket(ws: WebSocket):
    """WebSocket for real-time dashboard updates."""
    await ws.accept()
    call_manager.register_dashboard_socket(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        call_manager.unregister_dashboard_socket(ws)


# --- Dashboard API ---

@app.get("/dashboard/api/status")
async def dashboard_status():
    """Return current system status for the dashboard."""
    from src.data.mock_fleet import get_all_drivers, get_driver_hours, get_recent_events

    drivers = []
    for d in get_all_drivers():
        hours = get_driver_hours(d["driver_id"])
        events = get_recent_events(d["driver_id"])
        active_call = call_manager.get_active_call(d["driver_id"])
        drivers.append({
            "driver_id": d["driver_id"],
            "first_name": d["first_name"],
            "last_name": d["last_name"],
            "vehicle_rego": d["vehicle_rego"],
            "current_route": d.get("current_route", ""),
            "hours_driven": hours["hours_driven_continuous"] if hours else 0,
            "minutes_to_break": hours["minutes_until_mandatory_break"] if hours else 0,
            "recent_event_count": len(events),
            "on_call": active_call is not None,
        })

    return {
        "drivers": drivers,
        "active_calls": call_manager.get_all_active_calls(),
        "event_log": event_log[-50:],  # Last 50 events
        "config": {
            "telephony_provider": "browser",
        },
    }


@app.get("/dashboard/api/transcript/{driver_id}")
async def get_transcript(driver_id: str):
    """Return transcript for an active or recently ended call."""
    transcript, status = call_manager.get_transcript(driver_id)
    return {"transcript": transcript, "status": status}


class ShiftRequest(BaseModel):
    driver_id: str
    num_events: int = 5
    clear_memory: bool = True


@app.post("/api/triggers/simulate-shift")
async def simulate_shift(req: ShiftRequest):
    """Start a compressed shift simulation with random events."""
    from src.call.shift_simulator import run_shift_simulation, is_shift_running
    if is_shift_running(req.driver_id):
        return JSONResponse(status_code=409, content={"error": "Shift already running"})
    if req.num_events < 2 or req.num_events > 15:
        return JSONResponse(status_code=400, content={"error": "num_events must be 2-15"})
    asyncio.create_task(run_shift_simulation(
        driver_id=req.driver_id,
        num_events=req.num_events,
        call_manager=call_manager,
        clear_memory_first=req.clear_memory,
    ))
    return {"status": "shift_started", "driver_id": req.driver_id, "num_events": req.num_events}


@app.post("/api/triggers/stop-shift/{driver_id}")
async def stop_shift(driver_id: str):
    """Stop a running shift simulation."""
    from src.call.shift_simulator import stop_shift as _stop
    if _stop(driver_id):
        return {"status": "stopping", "driver_id": driver_id}
    return {"status": "no_shift_running"}


@app.get("/api/personas")
async def get_personas():
    """Return available driver persona presets."""
    import json
    personas_path = os.path.join(os.path.dirname(__file__), "..", "data", "mock", "driver_personas.json")
    with open(personas_path, "r") as f:
        return json.load(f)


class CardRequest(BaseModel):
    driver_id: str
    card_type: str  # rest_stop | wellness | incident
    scenario: str = ""


@app.post("/api/cards/generate")
async def generate_card(req: CardRequest):
    """Generate a sample visual card for demo purposes."""
    from src.data.mock_fleet import get_driver
    from src.cards.rest_stop_card import generate_rest_stop_card
    from src.cards.wellness_card import generate_wellness_card
    from src.cards.incident_card import generate_incident_card

    driver = get_driver(req.driver_id)
    if not driver:
        return JSONResponse(status_code=404, content={"error": f"Unknown driver: {req.driver_id}"})

    name = driver["first_name"]
    rego = driver.get("vehicle_rego", "")
    route = driver.get("current_route", "")

    if req.card_type == "rest_stop":
        scenarios = {
            "southern_cross": ("Southern Cross Truck Bay", 45,
                "You've been going strong, {name} — a quick cuppa and stretch at Southern Cross will do you the world of good."),
            "coolgardie": ("Coolgardie Rest Area", 85,
                "There's a nice spot coming up at Coolgardie with shade and water. Perfect for a breather, {name}."),
            "mt_magnet": ("Mt Magnet Roadhouse", 30,
                "Mt Magnet's just up the road, {name}. Fuel up the truck and yourself — they do a decent pie there."),
            "whim_creek": ("Whim Creek Roadhouse", 60,
                "Whim Creek's got everything you need, {name}. Pull in, grab a feed, and rest those eyes for a bit."),
        }
        s = scenarios.get(req.scenario, scenarios["southern_cross"])
        url = generate_rest_stop_card(req.driver_id, name, s[0], s[1], s[2].format(name=name))
        return {"image_url": url, "card_type": "rest_stop"}

    elif req.card_type == "wellness":
        scenarios = {
            "good_shift": {
                "results": [
                    {"hour": 0.8, "trigger": "companion_check_in", "status": "completed", "turns": 6, "duration": 32},
                    {"hour": 3.5, "trigger": "fatigue_camera", "status": "completed", "turns": 8, "duration": 45},
                    {"hour": 6.2, "trigger": "break_limit", "status": "completed", "turns": 4, "duration": 22},
                    {"hour": 9.0, "trigger": "driver_initiated", "status": "completed", "turns": 6, "duration": 38},
                    {"hour": 12.5, "trigger": "fatigue_camera", "status": "completed", "turns": 8, "duration": 50},
                ],
                "message": "Great shift today, {name}. You pulled over when it mattered and kept your cool on a long run. Rest up tonight.",
            },
            "tough_shift": {
                "results": [
                    {"hour": 0.5, "trigger": "companion_check_in", "status": "completed", "turns": 4, "duration": 20},
                    {"hour": 2.0, "trigger": "fatigue_camera", "status": "completed", "turns": 6, "duration": 35},
                    {"hour": 4.5, "trigger": "erratic_driving", "status": "completed", "turns": 8, "duration": 48},
                    {"hour": 5.5, "trigger": "break_limit", "status": "completed", "turns": 4, "duration": 25},
                    {"hour": 7.0, "trigger": "fatigue_camera", "status": "completed", "turns": 6, "duration": 40},
                    {"hour": 9.5, "trigger": "erratic_driving", "status": "completed", "turns": 8, "duration": 52},
                    {"hour": 11.0, "trigger": "fatigue_camera", "status": "completed", "turns": 6, "duration": 38},
                    {"hour": 13.0, "trigger": "fatigue_camera", "status": "completed", "turns": 8, "duration": 55},
                ],
                "message": "Tough one today, {name}. I know I was on your case a bit, but you got through it safe. That's what counts.",
            },
            "short_shift": {
                "results": [
                    {"hour": 1.0, "trigger": "companion_check_in", "status": "completed", "turns": 6, "duration": 30},
                    {"hour": 3.5, "trigger": "fatigue_camera", "status": "completed", "turns": 4, "duration": 20},
                    {"hour": 5.5, "trigger": "companion_check_in", "status": "completed", "turns": 4, "duration": 18},
                ],
                "message": "Smooth run today, {name}. Short and sweet. Enjoy the rest of your arvo.",
            },
        }
        s = scenarios.get(req.scenario, scenarios["good_shift"])
        url = generate_wellness_card(req.driver_id, name, s["results"], 180.0,
                                     s["message"].format(name=name))
        return {"image_url": url, "card_type": "wellness"}

    elif req.card_type == "incident":
        scenarios = {
            "microsleep": {
                "trigger_type": "fatigue_camera",
                "trigger_data": {"fatigue_event_type": "head_nod", "severity": "high"},
                "urgency": "high",
                "reason": f"Driver showing signs of microsleep — head nodding detected. {name} refused to pull over despite repeated suggestions. Immediate intervention recommended.",
            },
            "phone": {
                "trigger_type": "fatigue_camera",
                "trigger_data": {"fatigue_event_type": "phone_use", "severity": "medium"},
                "urgency": "medium",
                "reason": f"{name} was using their phone while driving. Acknowledged the behaviour but seemed dismissive. May need a reminder about company policy.",
            },
            "lane_drift": {
                "trigger_type": "erratic_driving",
                "trigger_data": {"erratic_sub_type": "lane_deviation"},
                "urgency": "medium",
                "reason": f"Lane deviation detected. {name} sounded tired and vague during the call. Agreed to pull over but seemed uncertain about when.",
            },
            "rollover": {
                "trigger_type": "erratic_driving",
                "trigger_data": {"erratic_sub_type": "rollover_intervention", "g_force": 0.8},
                "urgency": "high",
                "reason": f"Electronic stability intervention triggered on a curve. {name} was shaken but insisted on continuing. Load may have shifted — inspection recommended before resuming.",
            },
        }
        s = scenarios.get(req.scenario, scenarios["microsleep"])
        url = generate_incident_card(
            req.driver_id, name, s["trigger_type"], s["trigger_data"],
            s["urgency"], s["reason"], vehicle_rego=rego, route=route,
        )
        return {"image_url": url, "card_type": "incident"}

    return JSONResponse(status_code=400, content={"error": f"Unknown card type: {req.card_type}"})


@app.post("/dashboard/api/end-call/{driver_id}")
async def end_call(driver_id: str):
    """End an active call from the dashboard."""
    call = call_manager.end_call(driver_id)
    if call:
        return {"status": "ended", "call_id": call.call_id}
    return {"status": "no_call"}


# --- Video preview API (demo) ---

VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "mock", "videos")


@app.get("/api/videos/{driver}/{filename}")
async def get_video(driver: str, filename: str):
    """Serve a fatigue/erratic camera video file."""
    # Sanitise path components
    if ".." in driver or ".." in filename:
        return JSONResponse(status_code=400, content={"error": "Invalid path"})
    path = os.path.join(VIDEOS_DIR, driver, filename)
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "Video not found"})
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/videos/frames")
async def get_video_frames(event_type: str, severity: Optional[str] = None,
                           driver_id: Optional[str] = None, max_frames: int = 8):
    """Extract and return JPEG frames as base64 for preview."""
    from src.call.video_frames import extract_frames
    frames = extract_frames(event_type, severity, target_fps=1.0, driver_id=driver_id)
    if not frames:
        return {"frames": [], "count": 0}
    # Limit frame count and encode as base64 data URIs
    step = max(1, len(frames) // max_frames)
    selected = frames[::step][:max_frames]
    b64_frames = [base64.b64encode(f).decode("ascii") for f in selected]
    return {"frames": b64_frames, "count": len(frames), "returned": len(b64_frames)}


# --- Blog ---

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")


@app.get("/blog/{slug}.html")
async def blog_post(slug: str):
    """Render a markdown blog post from docs/ as HTML."""
    if ".." in slug or "/" in slug or "\\" in slug:
        return JSONResponse(status_code=400, content={"error": "Invalid slug"})
    md_path = os.path.join(DOCS_DIR, f"{slug}.md")
    if not os.path.exists(md_path):
        return JSONResponse(status_code=404, content={"error": "Post not found"})
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()
    html_body = markdown.markdown(md_content, extensions=["extra", "codehilite", "toc"])
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Betty AI — Blog</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.7;
         color: #1a1a1a; background: #fafafa; }}
  h1 {{ font-size: 2em; margin-bottom: 0.3em; }}
  h2 {{ margin-top: 2em; border-bottom: 1px solid #ddd; padding-bottom: 0.3em; }}
  blockquote {{ border-left: 4px solid #e67e22; margin: 1.5em 0; padding: 0.5em 1em;
                background: #fff8f0; font-style: italic; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
  pre code {{ display: block; padding: 1em; overflow-x: auto; }}
  a {{ color: #2980b9; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 2em 0; }}
  img {{ max-width: 100%; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
    return HTMLResponse(content=html)


# --- Root redirect ---

@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))


@app.get("/demo")
async def demo():
    """Interactive guided demo for judges."""
    return FileResponse(os.path.join(STATIC_DIR, "demo.html"))


if __name__ == "__main__":
    import uvicorn
    config = load_config()
    uvicorn.run(
        "src.main:app",
        host=config.get("server", {}).get("host", "0.0.0.0"),
        port=config.get("server", {}).get("port", 8000),
        reload=True,
    )
