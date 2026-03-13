"""Event router: receives events, runs risk assessment, initiates calls."""

import logging
from typing import Optional

from src.call.call_manager import CallManager
from src.data.mock_fleet import get_recent_events

logger = logging.getLogger(__name__)

# Base risk scores by severity
_SEVERITY_SCORES = {
    "low": 0.3,
    "medium": 0.6,
    "high": 0.9,
}

# Fatigue event type modifiers
_FATIGUE_TYPE_MODIFIERS = {
    "yawning": 0.0,
    "distraction": 0.05,
    "droopy_eyes": 0.1,
    "head_nod": 0.2,
    "phone_use": 0.1,
    "smoking": -0.05,
}

# Erratic driving sub-type scores
_ERRATIC_SCORES = {
    "lane_deviation": 0.5,
    "harsh_braking": 0.4,
    "excessive_sway": 0.7,
    "rollover_intervention": 0.95,
}


def assess_risk(trigger_type: str, trigger_data: dict, driver_id: str) -> dict:
    """Score an event and return risk assessment."""
    score = 0.5
    reasoning = ""

    if trigger_type == "fatigue_camera":
        severity = trigger_data.get("severity", "medium")
        fatigue_type = trigger_data.get("fatigue_event_type", "")
        base = _SEVERITY_SCORES.get(severity, 0.5)
        modifier = _FATIGUE_TYPE_MODIFIERS.get(fatigue_type, 0.0)
        score = min(1.0, base + modifier)

        # Consecutive event escalation
        recent = get_recent_events(driver_id, hours_back=1.0)
        if len(recent) >= 3:
            score = min(1.0, score + 0.2)

        reasoning = (
            f"Fatigue event: {fatigue_type} at {severity} severity. "
            f"Base {base:.2f} + modifier {modifier:+.2f} = {score:.2f}. "
            f"Recent events (1h): {len(recent)}."
        )

    elif trigger_type == "erratic_driving":
        sub_type = trigger_data.get("erratic_sub_type", "")
        score = _ERRATIC_SCORES.get(sub_type, 0.5)
        g_force = trigger_data.get("g_force")
        if g_force and g_force > 0.5:
            score = min(1.0, score + 0.1)
        if g_force and g_force > 0.8:
            score = min(1.0, score + 0.1)
        reasoning = f"Erratic driving: {sub_type}. G-force: {g_force or 'N/A'}. Score: {score:.2f}."

    elif trigger_type == "break_limit":
        from src.data.mock_fleet import get_driver_hours
        hours = get_driver_hours(driver_id)
        if hours:
            mins = hours["minutes_until_mandatory_break"]
            if mins <= 15:
                score = 0.8
            elif mins <= 30:
                score = 0.6
            else:
                score = 0.4
            reasoning = f"Break limit: {mins:.0f} min remaining. Score: {score:.2f}."
        else:
            score = 0.5
            reasoning = "Break limit check, no hours data."

    elif trigger_type == "companion_check_in":
        score = 0.2
        reasoning = "Companion check-in. Low priority."

    # Convert to priority (1=highest)
    if score >= 0.9:
        priority = 1
    elif score >= 0.7:
        priority = 2
    elif score >= 0.5:
        priority = 3
    elif score >= 0.3:
        priority = 4
    else:
        priority = 5

    return {
        "score": score,
        "priority": priority,
        "should_call": True,
        "reasoning": reasoning,
    }


async def assess_and_call(
    call_manager: CallManager,
    driver_id: str,
    trigger_type: str,
    trigger_data: dict,
    event_log: list[dict],
) -> dict:
    """Assess risk and initiate call if warranted."""
    risk = assess_risk(trigger_type, trigger_data, driver_id)

    if not risk["should_call"]:
        return {"status": "no_call", "risk": risk}

    # Initiate call
    call = call_manager.initiate_call(driver_id, trigger_type, trigger_data)

    # Notify driver's browser
    notified = await call_manager.notify_driver(driver_id, {
        "type": "incoming_call",
        "call_id": call.call_id,
        "trigger_type": trigger_type,
    })

    # Notify dashboard
    from datetime import datetime, timezone
    await call_manager.broadcast_to_dashboard({
        "type": "call_initiated",
        "driver_id": driver_id,
        "call_id": call.call_id,
        "trigger_type": trigger_type,
        "risk_score": risk["score"],
    })

    event_log.append({
        "type": "call",
        "message": f"Call initiated for {driver_id} (score={risk['score']:.2f}, priority={risk['priority']})",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "status": "call_initiated",
        "call_id": call.call_id,
        "driver_notified": notified,
        "risk": risk,
    }
