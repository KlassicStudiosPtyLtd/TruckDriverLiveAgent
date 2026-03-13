"""Erratic driving event handler."""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.data.mock_fleet import add_event

logger = logging.getLogger(__name__)


def process_driving_event(
    driver_id: str,
    sub_type: str,
    g_force: Optional[float] = None,
) -> dict:
    """Process an erratic driving event and store it."""
    event = {
        "type": "erratic_driving",
        "sub_type": sub_type,
        "g_force": g_force,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": f"Erratic driving: {sub_type}" + (f" ({g_force}g)" if g_force else ""),
    }
    add_event(driver_id, event)
    logger.info("Driving event processed: %s for %s", sub_type, driver_id)
    return event
