"""Mock driver profiles, hours data, and event history for demo purposes.

All data is realistic for Australian long-haul trucking operations.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# --- Load driver profiles from sample_data.json ---

_SAMPLE_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "mock", "sample_data.json"
)

def _load_sample_data() -> dict:
    with open(_SAMPLE_DATA_PATH, "r") as f:
        return json.load(f)

_SAMPLE_DATA = _load_sample_data()

MOCK_DRIVERS = {d["driver_id"]: d for d in _SAMPLE_DATA["drivers"]}
REST_AREAS = _SAMPLE_DATA.get("rest_areas", [])
FLEET_MANAGERS = _SAMPLE_DATA.get("fleet_managers", [])
VEHICLES = {v["vehicle_id"]: v for v in _SAMPLE_DATA.get("vehicles", [])}


def _now():
    return datetime.now(timezone.utc)


def _find_next_rest_area(route: str) -> tuple[Optional[str], Optional[float]]:
    """Find a rest area on the given route."""
    for ra in REST_AREAS:
        if ra["route"] in route:
            return ra["name"], float(ra["km_marker"])
    return None, None


def _initial_hours():
    """Generate initial hours state per driver."""
    now = _now()
    hours = {}
    defaults = [
        {"id": "DRV-001", "continuous": 3.5, "to_break": 90, "shift_remaining": 6.5, "shift_offset": 3.5},
        {"id": "DRV-002", "continuous": 4.25, "to_break": 45, "shift_remaining": 4.0, "shift_offset": 6.0},
        {"id": "DRV-003", "continuous": 1.75, "to_break": 195, "shift_remaining": 10.0, "shift_offset": 1.75},
    ]
    for d in defaults:
        driver = MOCK_DRIVERS.get(d["id"])
        rest_name, rest_km = (None, None)
        if driver:
            rest_name, rest_km = _find_next_rest_area(driver.get("current_route", ""))
        hours[d["id"]] = {
            "driver_id": d["id"],
            "hours_driven_continuous": d["continuous"],
            "max_continuous_hours": 5.0,
            "minutes_until_mandatory_break": d["to_break"],
            "next_rest_area_km": rest_km or 45.0,
            "next_rest_area_name": rest_name or "Unknown",
            "shift_hours_remaining": d["shift_remaining"],
            "shift_start_time": (now - timedelta(hours=d["shift_offset"])).isoformat(),
            "last_break_time": (now - timedelta(hours=d["continuous"])).isoformat(),
        }
    return hours


def _initial_events():
    """Generate sample event history."""
    now = _now()
    return {
        "DRV-001": [
            {
                "type": "fatigue",
                "event_type": "yawning",
                "severity": "low",
                "timestamp": (now - timedelta(hours=2, minutes=15)).isoformat(),
                "description": "Yawning detected near Merredin",
            },
        ],
        "DRV-002": [
            {
                "type": "fatigue",
                "event_type": "droopy_eyes",
                "severity": "medium",
                "timestamp": (now - timedelta(hours=1, minutes=30)).isoformat(),
                "description": "Droopy eyes detected south of Cue",
            },
            {
                "type": "erratic_driving",
                "sub_type": "lane_deviation",
                "g_force": 0.25,
                "timestamp": (now - timedelta(minutes=45)).isoformat(),
                "description": "Lane deviation near Cue",
            },
        ],
        "DRV-003": [],
    }


# Mutable state
_driver_hours: dict = {}
_event_history: dict = {}


def _ensure_loaded():
    if not _driver_hours:
        _driver_hours.update(_initial_hours())
    if not _event_history:
        _event_history.update(_initial_events())


# --- Public API ---

def get_all_drivers() -> list[dict]:
    """Return all mock driver profiles."""
    return list(MOCK_DRIVERS.values())


def get_driver(driver_id: str) -> Optional[dict]:
    """Return a single driver profile by ID."""
    return MOCK_DRIVERS.get(driver_id)


def get_driver_hours(driver_id: str) -> Optional[dict]:
    """Return current driving hours for a driver."""
    _ensure_loaded()
    if driver_id not in _driver_hours:
        now = _now()
        driver = MOCK_DRIVERS.get(driver_id)
        rest_name, rest_km = (None, None)
        if driver:
            rest_name, rest_km = _find_next_rest_area(driver.get("current_route", ""))
        _driver_hours[driver_id] = {
            "driver_id": driver_id,
            "hours_driven_continuous": 2.0,
            "max_continuous_hours": 5.0,
            "minutes_until_mandatory_break": 180,
            "next_rest_area_km": rest_km,
            "next_rest_area_name": rest_name,
            "shift_hours_remaining": 8.0,
            "shift_start_time": (now - timedelta(hours=2)).isoformat(),
            "last_break_time": None,
        }
    return _driver_hours.get(driver_id)


def update_driver_hours(driver_id: str, **kwargs) -> Optional[dict]:
    """Update specific fields on a driver's hours record."""
    hours = get_driver_hours(driver_id)
    if hours is None:
        return None
    hours.update(kwargs)
    return hours


def get_recent_events(driver_id: str, hours_back: float = 6.0) -> list[dict]:
    """Return recent events for a driver within the given time window."""
    _ensure_loaded()
    events = _event_history.get(driver_id, [])
    cutoff = (_now() - timedelta(hours=hours_back)).isoformat()
    return [e for e in events if e.get("timestamp", "") >= cutoff]


def add_event(driver_id: str, event: dict) -> None:
    """Add an event to a driver's history."""
    _ensure_loaded()
    if driver_id not in _event_history:
        _event_history[driver_id] = []
    _event_history[driver_id].append(event)
    logger.info("Added event for %s: %s", driver_id, event.get("type", "unknown"))


def check_break_limit(driver_id: str, warning_threshold_minutes: int = 30) -> Optional[dict]:
    """Check if a driver is approaching their mandatory break limit."""
    hours = get_driver_hours(driver_id)
    if hours is None:
        return None

    if hours["minutes_until_mandatory_break"] <= warning_threshold_minutes:
        return {
            "driver_id": driver_id,
            "hours_driven_continuous": hours["hours_driven_continuous"],
            "max_continuous_hours": hours["max_continuous_hours"],
            "minutes_until_mandatory_break": hours["minutes_until_mandatory_break"],
            "next_rest_area_km": hours.get("next_rest_area_km"),
            "next_rest_area_name": hours.get("next_rest_area_name"),
            "shift_hours_remaining": hours["shift_hours_remaining"],
        }
    return None


def get_fleet_manager() -> Optional[dict]:
    """Return the fleet manager info."""
    return FLEET_MANAGERS[0] if FLEET_MANAGERS else None


def get_vehicle(vehicle_id: str) -> Optional[dict]:
    """Return vehicle info by ID."""
    return VEHICLES.get(vehicle_id)


def reset_all():
    """Reset all mutable state (for testing)."""
    _driver_hours.clear()
    _event_history.clear()
