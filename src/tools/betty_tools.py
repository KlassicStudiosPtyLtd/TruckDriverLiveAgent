"""Tool definitions and handlers for Gemini Live API function calling."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from google.genai import types

from src.data.mock_fleet import get_driver, get_driver_hours, get_recent_events

logger = logging.getLogger(__name__)


# --- Gemini Function Declarations ---

TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_driver_hours",
        description=(
            "Get the driver's current hours driven, time until mandatory break, "
            "nearest rest area, and shift status."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "driver_id": types.Schema(
                    type="STRING",
                    description="The driver's ID",
                ),
            },
            required=["driver_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_recent_events",
        description=(
            "Get recent fatigue and driving events for this driver. "
            "Returns a list of events from the past N hours."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "driver_id": types.Schema(
                    type="STRING",
                    description="The driver's ID",
                ),
                "hours_back": types.Schema(
                    type="NUMBER",
                    description="How many hours back to look, default 6",
                ),
            },
            required=["driver_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="escalate_to_manager",
        description=(
            "Alert the fleet manager that this driver needs human intervention. "
            "Use when the driver shows concerning signs of fatigue and refuses to take a break."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "driver_id": types.Schema(
                    type="STRING",
                    description="The driver's ID",
                ),
                "reason": types.Schema(
                    type="STRING",
                    description="Why escalation is needed",
                ),
                "urgency": types.Schema(
                    type="STRING",
                    description="Urgency level: low, medium, or high",
                    enum=["low", "medium", "high"],
                ),
            },
            required=["driver_id", "reason", "urgency"],
        ),
    ),
    types.FunctionDeclaration(
        name="log_conversation_summary",
        description=(
            "Log a summary of the conversation after the call ends. "
            "Include your assessment of the driver's fatigue level and any actions taken."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "driver_id": types.Schema(
                    type="STRING",
                    description="The driver's ID",
                ),
                "summary": types.Schema(
                    type="STRING",
                    description="Brief summary of the conversation",
                ),
                "fatigue_assessment": types.Schema(
                    type="STRING",
                    description="Assessment: alert, mildly_tired, fatigued, dangerously_fatigued",
                ),
                "action_taken": types.Schema(
                    type="STRING",
                    description="What action was taken: none, encouraged_break, escalated",
                ),
            },
            required=["driver_id", "summary", "fatigue_assessment", "action_taken"],
        ),
    ),
    types.FunctionDeclaration(
        name="assess_driver_mood",
        description=(
            "Log your assessment of the driver's current emotional state and mood. "
            "Call this during the conversation when you've formed an impression of how "
            "the driver is feeling. This helps you adapt in future calls."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "driver_id": types.Schema(
                    type="STRING",
                    description="The driver's ID",
                ),
                "mood": types.Schema(
                    type="STRING",
                    description="The driver's mood",
                    enum=["cheerful", "neutral", "grumpy", "anxious",
                          "lonely", "stressed", "homesick", "defiant",
                          "exhausted", "shaken"],
                ),
                "confidence": types.Schema(
                    type="STRING",
                    description="How confident you are in this assessment",
                    enum=["low", "medium", "high"],
                ),
                "notes": types.Schema(
                    type="STRING",
                    description="Brief notes on what gave you this impression (tone, words, pace)",
                ),
            },
            required=["driver_id", "mood", "confidence"],
        ),
    ),
    types.FunctionDeclaration(
        name="send_rest_stop_card",
        description=(
            "Send a visual rest stop recommendation card to the driver's dashboard. "
            "Call this when you recommend the driver pull over at a specific rest area. "
            "The card shows the rest area name, distance, facilities, and your message."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "driver_id": types.Schema(
                    type="STRING",
                    description="The driver's ID",
                ),
                "rest_area_name": types.Schema(
                    type="STRING",
                    description="Name of the rest area you're recommending",
                ),
                "distance_km": types.Schema(
                    type="NUMBER",
                    description="Approximate distance to the rest area in km",
                ),
                "message": types.Schema(
                    type="STRING",
                    description="Your warm, personalised message to the driver about stopping",
                ),
            },
            required=["driver_id", "rest_area_name", "distance_km", "message"],
        ),
    ),
]


# --- Callbacks ---

_escalation_callback: Optional[Callable] = None
_log_callback: Optional[Callable] = None
_card_callback: Optional[Callable] = None
_current_trigger_type: Optional[str] = None
_current_trigger_data: Optional[dict] = None


def set_escalation_callback(callback: Callable) -> None:
    """Register a callback for when escalate_to_manager is called."""
    global _escalation_callback
    _escalation_callback = callback


def set_log_callback(callback: Callable) -> None:
    """Register a callback for when log_conversation_summary is called."""
    global _log_callback
    _log_callback = callback


def set_card_callback(callback: Callable) -> None:
    """Register a callback for broadcasting card events to the dashboard."""
    global _card_callback
    _card_callback = callback


def set_trigger_context(trigger_type: str, trigger_data: dict) -> None:
    """Store the current call's trigger context for use by tool handlers."""
    global _current_trigger_type, _current_trigger_data
    _current_trigger_type = trigger_type
    _current_trigger_data = trigger_data


# --- Tool Handler ---

async def handle_tool_call(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool call from Gemini and return the result."""
    logger.info("Tool call: %s with input: %s", tool_name, tool_input)

    handlers = {
        "get_driver_hours": _handle_get_driver_hours,
        "get_recent_events": _handle_get_recent_events,
        "escalate_to_manager": _handle_escalate_to_manager,
        "log_conversation_summary": _handle_log_conversation_summary,
        "assess_driver_mood": _handle_assess_driver_mood,
        "send_rest_stop_card": _handle_send_rest_stop_card,
    }

    handler = handlers.get(tool_name)
    if handler is None:
        logger.error("Unknown tool: %s", tool_name)
        return {"error": f"Unknown tool: {tool_name}"}

    return await handler(tool_input)


async def _handle_get_driver_hours(input: dict[str, Any]) -> dict[str, Any]:
    """Handle get_driver_hours tool call."""
    driver_id = input.get("driver_id", "")
    hours = get_driver_hours(driver_id)
    if hours is None:
        return {"error": f"No hours data for driver {driver_id}"}
    return {
        "hours_driven_continuous": hours["hours_driven_continuous"],
        "max_continuous_hours": hours["max_continuous_hours"],
        "minutes_until_mandatory_break": hours["minutes_until_mandatory_break"],
        "next_rest_area": hours.get("next_rest_area_name") or "Unknown",
        "next_rest_area_km": hours.get("next_rest_area_km"),
        "shift_hours_remaining": hours["shift_hours_remaining"],
    }


async def _handle_get_recent_events(input: dict[str, Any]) -> dict[str, Any]:
    """Handle get_recent_events tool call."""
    driver_id = input.get("driver_id", "")
    hours_back = input.get("hours_back", 6.0)
    events = get_recent_events(driver_id, hours_back)
    return {"driver_id": driver_id, "events": events, "count": len(events)}


async def _handle_escalate_to_manager(input: dict[str, Any]) -> dict[str, Any]:
    """Handle escalate_to_manager tool call + generate incident card."""
    driver_id = input.get("driver_id", "")
    reason = input.get("reason", "")
    urgency = input.get("urgency", "medium")

    logger.warning(
        "ESCALATION: driver=%s reason=%s urgency=%s",
        driver_id, reason, urgency,
    )

    if _escalation_callback:
        await _escalation_callback(
            driver_id=driver_id,
            reason=reason,
            urgency=urgency,
        )

    # Generate incident card in background so Betty keeps talking
    driver = get_driver(driver_id)
    asyncio.create_task(_generate_incident_card_bg(
        driver_id, driver, urgency, reason,
    ))

    return {
        "status": "escalated",
        "driver_id": driver_id,
        "message": "Fleet manager has been notified.",
    }


async def _generate_incident_card_bg(
    driver_id: str, driver: dict | None, urgency: str, reason: str,
) -> None:
    """Background task: generate incident card and broadcast when ready."""
    try:
        from src.cards.incident_card import generate_incident_card
        driver_name = driver["first_name"] if driver else driver_id
        vehicle_rego = driver.get("vehicle_rego", "") if driver else ""
        route = driver.get("current_route", "") if driver else ""

        loop = asyncio.get_event_loop()
        card_url = await loop.run_in_executor(
            None,
            lambda: generate_incident_card(
                driver_id=driver_id,
                driver_name=driver_name,
                trigger_type=_current_trigger_type or "unknown",
                trigger_data=_current_trigger_data or {},
                urgency=urgency,
                reason=reason,
                vehicle_rego=vehicle_rego,
                route=route,
            ),
        )
        logger.info("Incident card generated (bg): %s", card_url)

        if _card_callback:
            await _card_callback(
                card_type="incident",
                driver_id=driver_id,
                image_url=card_url,
            )
    except Exception:
        logger.exception("Failed to generate incident card (bg)")


async def _handle_log_conversation_summary(input: dict[str, Any]) -> dict[str, Any]:
    """Handle log_conversation_summary tool call."""
    driver_id = input.get("driver_id", "")
    summary = input.get("summary", "")
    fatigue_assessment = input.get("fatigue_assessment", "")
    action_taken = input.get("action_taken", "")

    logger.info(
        "CALL LOG: driver=%s fatigue=%s action=%s summary=%s",
        driver_id, fatigue_assessment, action_taken, summary,
    )

    if _log_callback:
        await _log_callback(
            driver_id=driver_id,
            summary=summary,
            fatigue_assessment=fatigue_assessment,
            action_taken=action_taken,
        )

    return {"status": "logged", "driver_id": driver_id}


async def _handle_assess_driver_mood(input: dict[str, Any]) -> dict[str, Any]:
    """Handle assess_driver_mood tool call — persists mood to memory."""
    driver_id = input.get("driver_id", "")
    mood = input.get("mood", "neutral")
    confidence = input.get("confidence", "medium")
    notes = input.get("notes", "")

    logger.info(
        "MOOD ASSESSMENT: driver=%s mood=%s confidence=%s notes=%s",
        driver_id, mood, confidence, notes,
    )

    # Save mood to memory via the log callback so it persists
    if _log_callback:
        await _log_callback(
            driver_id=driver_id,
            summary=f"Mood assessment: {mood} ({confidence} confidence). {notes}",
            fatigue_assessment=mood if mood in ("exhausted",) else "",
            action_taken="mood_noted",
        )

    return {"status": "noted", "driver_id": driver_id, "mood": mood}


async def _handle_send_rest_stop_card(input: dict[str, Any]) -> dict[str, Any]:
    """Handle send_rest_stop_card tool call — generates card in background."""
    driver_id = input.get("driver_id", "")
    rest_area_name = input.get("rest_area_name", "Rest Area")
    distance_km = input.get("distance_km", 0)
    message = input.get("message", "Time for a break, mate.")

    driver = get_driver(driver_id)
    driver_name = driver["first_name"] if driver else driver_id

    # Fire off card generation in background so Betty keeps talking
    asyncio.create_task(_generate_rest_stop_card_bg(
        driver_id, driver_name, rest_area_name, distance_km, message,
    ))

    return {
        "status": "card_being_prepared",
        "driver_id": driver_id,
        "message": f"Rest stop card for {rest_area_name} is being generated and will appear on the driver's screen shortly.",
    }


async def _generate_rest_stop_card_bg(
    driver_id: str, driver_name: str, rest_area_name: str,
    distance_km: float, message: str,
) -> None:
    """Background task: generate rest stop card and broadcast when ready."""
    try:
        from src.cards.rest_stop_card import generate_rest_stop_card
        # Run sync card generation in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        card_url = await loop.run_in_executor(
            None,
            lambda: generate_rest_stop_card(
                driver_id=driver_id,
                driver_name=driver_name,
                rest_area_name=rest_area_name,
                distance_km=distance_km,
                message=message,
            ),
        )
        logger.info("Rest stop card generated (bg): %s", card_url)

        if _card_callback:
            await _card_callback(
                card_type="rest_stop",
                driver_id=driver_id,
                image_url=card_url,
            )
    except Exception:
        logger.exception("Failed to generate rest stop card (bg)")
