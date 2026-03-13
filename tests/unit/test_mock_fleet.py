"""Unit tests for mock fleet data — no API key needed."""

import pytest

from src.data.mock_fleet import (
    get_all_drivers, get_driver, get_driver_hours, get_recent_events,
    add_event, check_break_limit, get_fleet_manager, get_vehicle,
    reset_all,
)


@pytest.fixture(autouse=True)
def clean_state():
    """Reset mutable state before each test."""
    reset_all()
    yield
    reset_all()


class TestDriverProfiles:
    """Test driver profile lookup."""

    def test_get_all_drivers(self):
        drivers = get_all_drivers()
        assert len(drivers) == 3

    def test_get_driver_by_id(self):
        driver = get_driver("DRV-001")
        assert driver is not None
        assert driver["driver_id"] == "DRV-001"
        assert "first_name" in driver

    def test_get_driver_unknown(self):
        driver = get_driver("DRV-999")
        assert driver is None

    def test_driver_has_required_fields(self):
        driver = get_driver("DRV-001")
        for field in ["driver_id", "first_name", "last_name", "phone_number",
                      "vehicle_id", "vehicle_rego", "home_base", "current_route"]:
            assert field in driver, f"Missing field: {field}"


class TestDriverHours:
    """Test driving hours data."""

    def test_get_hours(self):
        hours = get_driver_hours("DRV-001")
        assert hours is not None
        assert "hours_driven_continuous" in hours
        assert "minutes_until_mandatory_break" in hours
        assert "shift_hours_remaining" in hours

    def test_hours_unknown_driver_creates_default(self):
        hours = get_driver_hours("DRV-999")
        assert hours is not None
        assert hours["hours_driven_continuous"] == 2.0

    def test_hours_has_rest_area(self):
        hours = get_driver_hours("DRV-001")
        assert "next_rest_area_name" in hours
        assert "next_rest_area_km" in hours


class TestEvents:
    """Test event history."""

    def test_get_recent_events(self):
        events = get_recent_events("DRV-001")
        assert isinstance(events, list)

    def test_add_event(self):
        from datetime import datetime, timezone
        initial = len(get_recent_events("DRV-001"))
        add_event("DRV-001", {
            "type": "fatigue",
            "event_type": "yawning",
            "severity": "low",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Test event",
        })
        assert len(get_recent_events("DRV-001")) == initial + 1

    def test_events_empty_for_new_driver(self):
        events = get_recent_events("DRV-003")
        assert events == []


class TestBreakLimit:
    """Test break limit checking."""

    def test_approaching_break_triggers(self):
        # DRV-002 has 45 min until break (< default threshold of 30 won't trigger,
        # but we can set a higher threshold)
        result = check_break_limit("DRV-002", warning_threshold_minutes=60)
        assert result is not None
        assert result["driver_id"] == "DRV-002"

    def test_distant_break_returns_none(self):
        # DRV-003 has 195 min until break
        result = check_break_limit("DRV-003", warning_threshold_minutes=30)
        assert result is None

    def test_unknown_driver(self):
        result = check_break_limit("DRV-999")
        # Creates default with 180 min — won't trigger at 30 min threshold
        assert result is None


class TestFleetManager:
    def test_get_fleet_manager(self):
        mgr = get_fleet_manager()
        assert mgr is not None
        assert "name" in mgr
        assert "phone" in mgr


class TestVehicles:
    def test_get_vehicle(self):
        v = get_vehicle("TRK-042")
        assert v is not None
        assert v["make"] == "Kenworth"

    def test_unknown_vehicle(self):
        assert get_vehicle("TRK-999") is None
