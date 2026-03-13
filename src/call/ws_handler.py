"""WebSocket handler bridging browser PCM audio to/from Gemini Live API.

Critical file: /call/{driver_id} endpoint.
Two async tasks: receive_from_browser + send_to_browser (via Gemini receive loop).
"""

import asyncio
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from src.call.call_manager import CallManager
from src.call.video_frames import extract_frames
from src.data.mock_fleet import get_driver, get_driver_hours, get_recent_events
from src.memory.store import add_entry as add_memory_entry, get_memory_summary
from src.tools.betty_tools import (
    TOOL_DECLARATIONS, handle_tool_call, set_log_callback,
    set_card_callback, set_trigger_context,
)
from src.voice.gemini_live import GeminiLiveSession
from src.voice.prompts import build_system_prompt

logger = logging.getLogger(__name__)


async def handle_driver_call(
    ws: WebSocket,
    driver_id: str,
    call_manager: CallManager,
) -> None:
    """Handle a voice call WebSocket connection from a driver's browser.

    Protocol:
    - Browser sends binary frames: raw 16-bit PCM at 16kHz mono
    - Server sends binary frames: raw 16-bit PCM at 24kHz mono
    - Server sends JSON frames: {"type": "transcript", "text": "..."} for transcription
    - Browser sends JSON: {"type": "hangup"} to end call
    """
    await ws.accept()

    # Look up driver and build context
    driver = get_driver(driver_id)
    if not driver:
        await ws.send_json({"type": "error", "message": f"Unknown driver: {driver_id}"})
        await ws.close()
        return

    call = call_manager.accept_call(driver_id)
    if not call:
        await ws.send_json({"type": "error", "message": "No pending call"})
        await ws.close()
        return

    trigger_type = call.trigger_type
    trigger_data = call.trigger_data

    # Build system prompt with full context + memory from previous calls
    hours = get_driver_hours(driver_id)
    events = get_recent_events(driver_id)
    event_summary = f"{len(events)} recent events" if events else None
    memory_summary = get_memory_summary(driver_id)

    system_prompt = build_system_prompt(
        driver_name=driver["first_name"],
        trigger_type=trigger_type,
        route=driver.get("current_route"),
        hours_driven=hours["hours_driven_continuous"] if hours else None,
        recent_event_summary=event_summary,
        memory_summary=memory_summary,
        fatigue_event_type=trigger_data.get("fatigue_event_type"),
        severity=trigger_data.get("severity"),
        erratic_sub_type=trigger_data.get("erratic_sub_type"),
        g_force=trigger_data.get("g_force"),
        hours_driven_continuous=hours["hours_driven_continuous"] if hours else None,
        minutes_until_mandatory_break=hours["minutes_until_mandatory_break"] if hours else None,
        next_rest_area_name=hours.get("next_rest_area_name") if hours else None,
        next_rest_area_km=hours.get("next_rest_area_km") if hours else None,
    )

    # Hook memory: when Betty calls log_conversation_summary, persist it
    async def _save_memory(**kwargs):
        add_memory_entry(
            driver_id=kwargs.get("driver_id", driver_id),
            summary=kwargs.get("summary", ""),
            fatigue_assessment=kwargs.get("fatigue_assessment", ""),
            action_taken=kwargs.get("action_taken", ""),
        )
    set_log_callback(_save_memory)

    # Set up card callback for broadcasting card events
    async def _on_card(**kwargs):
        await call_manager.broadcast_to_dashboard({
            "type": "card",
            "card_type": kwargs.get("card_type", ""),
            "driver_id": kwargs.get("driver_id", driver_id),
            "image_url": kwargs.get("image_url", ""),
        })
    set_card_callback(_on_card)
    set_trigger_context(trigger_type, trigger_data)

    # Audio callback: forward Gemini audio to browser
    async def on_audio(data: bytes):
        try:
            await ws.send_bytes(data)
        except Exception:
            pass

    # Transcript callback: forward text to browser and dashboard
    async def on_text(text: str):
        try:
            await ws.send_json({"type": "transcript", "speaker": "betty", "text": text})
            await call_manager.broadcast_to_dashboard({
                "type": "transcript",
                "driver_id": driver_id,
                "speaker": "betty",
                "text": text,
            })
        except Exception:
            pass

    async def on_turn_complete():
        try:
            await ws.send_json({"type": "turn_complete"})
        except Exception:
            pass

    async def on_interrupted():
        try:
            await ws.send_json({"type": "interrupted"})
        except Exception:
            pass

    # Create Gemini session with tools
    session = GeminiLiveSession(
        system_prompt=system_prompt,
        voice="Aoede",
        tools=TOOL_DECLARATIONS,
        tool_handler=handle_tool_call,
        on_audio=on_audio,
        on_text=on_text,
        on_turn_complete=on_turn_complete,
        on_interrupted=on_interrupted,
    )

    try:
        await session.connect()
        session.start_receiving()

        # Inject fatigue camera video frames into Betty's session
        if trigger_type in ("fatigue_camera", "erratic_driving"):
            event_key = trigger_data.get("fatigue_event_type") or trigger_data.get("erratic_sub_type", "")
            sev = trigger_data.get("severity")
            frames = extract_frames(event_key, sev, target_fps=1.0, driver_id=driver_id)
            if frames:
                logger.info("Injecting %d video frames into Betty's session", len(frames))
                for frame_bytes in frames:
                    await session.send_video_frame(frame_bytes)
                    await asyncio.sleep(0.1)
                logger.info("Video frames injected")

        await ws.send_json({"type": "call_connected", "call_id": call.call_id})
        await call_manager.broadcast_to_dashboard({
            "type": "call_started",
            "driver_id": driver_id,
            "call_id": call.call_id,
            "trigger_type": trigger_type,
        })

        # Receive audio from browser and forward to Gemini
        while True:
            message = await ws.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"]:
                await session.send_audio(message["bytes"])

            elif "text" in message:
                import json
                try:
                    data = json.loads(message["text"])
                    if data.get("type") == "hangup":
                        break
                except (json.JSONDecodeError, TypeError):
                    pass

    except WebSocketDisconnect:
        logger.info("Driver %s disconnected", driver_id)
    except Exception:
        logger.exception("Error in call handler for driver %s", driver_id)
    finally:
        await session.close()
        call_manager.end_call(driver_id)
        await call_manager.broadcast_to_dashboard({
            "type": "call_ended",
            "driver_id": driver_id,
        })
        logger.info("Call ended for driver %s", driver_id)
