"""Fatigue event handler — processes fatigue camera events."""

import logging
from datetime import datetime, timezone

from src.data.mock_fleet import add_event

logger = logging.getLogger(__name__)


def process_fatigue_event(
    driver_id: str,
    event_type: str,
    severity: str,
) -> dict:
    """Process a fatigue camera event and store it."""
    event = {
        "type": "fatigue",
        "event_type": event_type,
        "severity": severity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": f"Fatigue event: {event_type} ({severity})",
    }
    add_event(driver_id, event)
    logger.info("Fatigue event processed: %s for %s (%s)", event_type, driver_id, severity)
    return event
