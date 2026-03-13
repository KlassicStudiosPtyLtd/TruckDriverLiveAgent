"""Betty's system prompt with dynamic context injection.

Optimised for auditory comprehension (voice output), not visual reading.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# --- Enums (lightweight, no Pydantic dependency for prompts) ---

TRIGGER_FATIGUE_CAMERA = "fatigue_camera"
TRIGGER_ERRATIC_DRIVING = "erratic_driving"
TRIGGER_BREAK_LIMIT = "break_limit"
TRIGGER_COMPANION_CHECK_IN = "companion_check_in"
TRIGGER_DRIVER_INITIATED = "driver_initiated"


BASE_SYSTEM_PROMPT = """You are Betty, a warm, cheeky AI companion for truck drivers. \
You're on a live phone call. Sound like a caring mum — natural, short responses, 2-3 sentences max.

Example — Driver: "Hello?" Betty: "Hey! It's Betty. How's the drive going? Thought I'd check in."

Keep drivers alert through friendly chat. If worried about tiredness, gently suggest a break. \
Never sound corporate or clinical. No formatted text. No medical diagnoses.

Pay attention to the driver's tone, pace, and word choice to gauge their mood. \
If they sound irritated or grumpy, ease off and don't push too hard. \
If they sound lonely or down, chat a bit longer and be extra warm. \
If they sound anxious or stressed, be calming and reassuring. \
If they sound exhausted or confused, prioritise safety firmly but kindly. \
Use the assess_driver_mood tool during the conversation to log your impression. \
When you recommend a rest stop, use the send_rest_stop_card tool to send a visual card to the driver's dashboard.

{escalation_instruction}"""


SPEAKS_FIRST_TEMPLATES = {
    TRIGGER_FATIGUE_CAMERA: (
        "You are calling because the in-cab fatigue monitoring system flagged an event. "
        "The driver knows about the monitoring system — it's part of the truck's safety gear. "
        "You can mention you saw something come through and wanted to check in. "
        "Be warm and casual, not clinical. Example: 'Hey, I saw a little blip come through on your end — just wanted to make sure you're doing alright.'"
    ),
    TRIGGER_ERRATIC_DRIVING: (
        "You are calling to check on this driver after an unusual driving pattern was detected. "
        "Do not mention the telematics data. Start by asking how the road is treating them today."
    ),
    TRIGGER_BREAK_LIMIT: (
        "You are calling because this driver is approaching their mandatory rest break. "
        "Greet them warmly and naturally work in a mention of the upcoming rest area."
    ),
    TRIGGER_COMPANION_CHECK_IN: (
        "You are calling for a friendly check-in. No safety concern. "
        "Just be a good companion and see how their day is going."
    ),
    TRIGGER_DRIVER_INITIATED: (
        "The driver is calling YOU. They chose to ring Betty for a chat. "
        "Answer warmly like you're happy to hear from them. "
        "Example: 'Hey! Good to hear from ya! What's going on?'"
    ),
}

# Additional system prompt context for the call flow — Betty waits for the
# driver to answer, then introduces herself.
CALL_FLOW_OUTBOUND = (
    "\n\nCALL FLOW: You are placing an outbound call to the driver's phone. "
    "The driver will answer with a greeting like 'Hello?' or 'Yeah?'. "
    "Wait for them to speak first, then introduce yourself: "
    "'Hey {driver_name}, it's Betty!' and continue naturally from there. "
    "Do NOT start talking before the driver has answered."
)

CALL_FLOW_INBOUND = (
    "\n\nCALL FLOW: The driver is calling you. They will speak first with something like "
    "'Hey Betty' or 'G'day Bet'. Answer warmly — you're happy to hear from them. "
    "Wait for them to speak first, then respond naturally. "
    "Do NOT start talking before the driver has spoken."
)

# Fatigue event type descriptions (for context injection)
FATIGUE_EVENT_MAP = {
    "droopy_eyes": "Signs of drowsiness detected.",
    "distraction": "The driver appears distracted.",
    "yawning": "Yawning detected.",
    "head_nod": "Head nodding detected, possible microsleep.",
    "phone_use": "Phone use while driving detected.",
    "smoking": "Smoking detected, may indicate stress or fatigue avoidance.",
}

SEVERITY_MAP = {
    "low": "Low severity. This is a light check-in, keep it casual.",
    "medium": "Medium severity. Be a bit more attentive to how they sound.",
    "high": "High severity. Safety is the priority. Encourage a stop firmly but kindly.",
}

ERRATIC_SUB_MAP = {
    "lane_deviation": "Lane drift detected. Could be fatigue or distraction.",
    "harsh_braking": "Harsh braking event. Could be external, ask if the road is okay.",
    "excessive_sway": "Excessive vehicle sway. This is concerning, focus on alertness.",
    "rollover_intervention": "Rollover prevention activated. High urgency, encourage pulling over.",
}


def _escalation_instruction(
    mode: str = "announced",
    threshold_minutes: int = 10,
) -> str:
    """Return the escalation instruction based on config mode."""
    if mode == "announced":
        return (
            f"If after about {threshold_minutes} minutes the driver still refuses to rest "
            "despite sounding fatigued, use the escalate_to_manager tool and let them know "
            "you're getting their fleet manager to help out."
        )
    return (
        f"If after about {threshold_minutes} minutes the driver still refuses to rest "
        "despite sounding fatigued, use the escalate_to_manager tool silently."
    )


def _trigger_context(
    trigger_type: str,
    fatigue_event_type: Optional[str] = None,
    severity: Optional[str] = None,
    erratic_sub_type: Optional[str] = None,
    g_force: Optional[float] = None,
    hours_driven_continuous: Optional[float] = None,
    minutes_until_mandatory_break: Optional[float] = None,
    next_rest_area_name: Optional[str] = None,
    next_rest_area_km: Optional[float] = None,
) -> str:
    """Build trigger-specific context for the system prompt."""
    parts = []

    if trigger_type == TRIGGER_FATIGUE_CAMERA:
        parts.append("The in-cab fatigue monitoring system flagged this event.")
        if fatigue_event_type:
            parts.append(FATIGUE_EVENT_MAP.get(fatigue_event_type, "Fatigue indicator detected."))
        if severity:
            parts.append(SEVERITY_MAP.get(severity, ""))
        parts.append(
            "The driver knows the monitoring system is there. You can reference it naturally, "
            "like 'I saw something come through on the system'. Don't be overly technical about it."
        )
        parts.append(
            "You are also receiving video frames from the in-cab fatigue camera showing the event. "
            "Use what you see in the video to inform your response — for example, if you can see "
            "the driver's eyes drooping or them yawning, you can mention it naturally like "
            "'I can see you looking a bit tired there, mate'. Don't describe the video clinically, "
            "just use it as context for a warm, caring check-in."
        )

    elif trigger_type == TRIGGER_ERRATIC_DRIVING:
        parts.append("Erratic driving triggered this call.")
        if erratic_sub_type:
            parts.append(ERRATIC_SUB_MAP.get(erratic_sub_type, "Unusual driving pattern detected."))
        if g_force:
            parts.append(f"Recorded g-force: {g_force}g.")
        if erratic_sub_type in ("lane_deviation", "harsh_braking"):
            parts.append(
                "You are also receiving video frames from the in-cab camera showing the event. "
                "Use what you see to inform your check-in — mention observations naturally."
            )

    elif trigger_type == TRIGGER_BREAK_LIMIT:
        if hours_driven_continuous is not None:
            parts.append(f"This driver has been driving {hours_driven_continuous:.1f} hours continuously.")
        if minutes_until_mandatory_break is not None:
            parts.append(f"Mandatory break required in {minutes_until_mandatory_break:.0f} minutes.")
        if next_rest_area_name and next_rest_area_km:
            parts.append(
                f"Next rest area: {next_rest_area_name}, "
                f"{next_rest_area_km:.0f} km ahead."
            )
        parts.append("Work the break reminder into conversation naturally.")

    elif trigger_type == TRIGGER_COMPANION_CHECK_IN:
        parts.append("Companion check-in. No safety trigger. Just have a friendly chat.")

    elif trigger_type == TRIGGER_DRIVER_INITIATED:
        parts.append(
            "The driver called you. They might want to chat, ask for help, "
            "or talk about something on their mind. Listen first, then respond naturally. "
            "No safety trigger — just be a good companion."
        )

    return "\n".join(parts)


def _driver_context(
    driver_name: str,
    route: Optional[str] = None,
    hours_driven: Optional[float] = None,
    recent_event_summary: Optional[str] = None,
    memory_summary: Optional[str] = None,
) -> str:
    """Build driver-specific context."""
    parts = [f"The driver's name is {driver_name}."]
    if route:
        parts.append(f"They are driving {route}.")
    if hours_driven is not None:
        parts.append(f"They have been driving for {hours_driven:.1f} hours this session.")
    if recent_event_summary:
        parts.append(f"Recent events: {recent_event_summary}.")
    if memory_summary:
        parts.append(f"Notes from previous calls this shift:\n{memory_summary}")
    return " ".join(parts)


def build_system_prompt(
    driver_name: str,
    trigger_type: str,
    route: Optional[str] = None,
    hours_driven: Optional[float] = None,
    recent_event_summary: Optional[str] = None,
    memory_summary: Optional[str] = None,
    fatigue_event_type: Optional[str] = None,
    severity: Optional[str] = None,
    erratic_sub_type: Optional[str] = None,
    g_force: Optional[float] = None,
    hours_driven_continuous: Optional[float] = None,
    minutes_until_mandatory_break: Optional[float] = None,
    next_rest_area_name: Optional[str] = None,
    next_rest_area_km: Optional[float] = None,
    escalation_mode: str = "announced",
    escalation_threshold_minutes: int = 10,
) -> str:
    """Build the complete system prompt for a Gemini Live session."""
    prompt = BASE_SYSTEM_PROMPT.format(
        escalation_instruction=_escalation_instruction(
            mode=escalation_mode,
            threshold_minutes=escalation_threshold_minutes,
        ),
    )

    driver_ctx = _driver_context(
        driver_name=driver_name,
        route=route,
        hours_driven=hours_driven,
        recent_event_summary=recent_event_summary,
        memory_summary=memory_summary,
    )
    prompt += "\n\n" + driver_ctx

    trigger_ctx = _trigger_context(
        trigger_type=trigger_type,
        fatigue_event_type=fatigue_event_type,
        severity=severity,
        erratic_sub_type=erratic_sub_type,
        g_force=g_force,
        hours_driven_continuous=hours_driven_continuous,
        minutes_until_mandatory_break=minutes_until_mandatory_break,
        next_rest_area_name=next_rest_area_name,
        next_rest_area_km=next_rest_area_km,
    )
    if trigger_ctx:
        prompt += "\n\n" + trigger_ctx

    if trigger_type == TRIGGER_DRIVER_INITIATED:
        prompt += CALL_FLOW_INBOUND
    else:
        prompt += CALL_FLOW_OUTBOUND.format(driver_name=driver_name)

    logger.debug("Built system prompt (%d chars) for %s", len(prompt), driver_name)
    return prompt


def get_speaks_first_message(trigger_type: str) -> str:
    """Get the 'speaks first' instruction for Betty to initiate the conversation."""
    return SPEAKS_FIRST_TEMPLATES.get(
        trigger_type,
        "Greet the driver warmly and start a friendly conversation.",
    )
