"""Unit tests for system prompt building — no API key needed."""

import pytest

from src.voice.prompts import (
    build_system_prompt,
    get_speaks_first_message,
    TRIGGER_FATIGUE_CAMERA,
    TRIGGER_ERRATIC_DRIVING,
    TRIGGER_BREAK_LIMIT,
    TRIGGER_COMPANION_CHECK_IN,
    TRIGGER_DRIVER_INITIATED,
)


class TestBuildSystemPrompt:
    """Test system prompt construction."""

    def test_contains_betty_identity(self):
        prompt = build_system_prompt("Dazza", "companion_check_in")
        assert "Betty" in prompt

    def test_contains_driver_name(self):
        prompt = build_system_prompt("Dazza", "companion_check_in")
        assert "Dazza" in prompt

    def test_contains_route(self):
        prompt = build_system_prompt(
            "Dazza", "companion_check_in",
            route="Perth to Coolgardie via Great Eastern Highway",
        )
        assert "Perth to Coolgardie" in prompt

    def test_contains_hours_driven(self):
        prompt = build_system_prompt(
            "Dazza", "companion_check_in", hours_driven=4.5,
        )
        assert "4.5 hours" in prompt

    def test_fatigue_camera_context(self):
        prompt = build_system_prompt(
            "Dazza", TRIGGER_FATIGUE_CAMERA,
            fatigue_event_type="droopy_eyes", severity="high",
        )
        assert "fatigue monitoring" in prompt.lower() or "fatigue" in prompt.lower()
        assert "High severity" in prompt
        assert "drowsiness" in prompt.lower() or "droopy" in prompt.lower()

    def test_erratic_driving_context(self):
        prompt = build_system_prompt(
            "Dazza", TRIGGER_ERRATIC_DRIVING,
            erratic_sub_type="lane_deviation",
        )
        assert "Lane drift" in prompt or "lane" in prompt.lower()
        assert "erratic" in prompt.lower()

    def test_break_limit_context(self):
        prompt = build_system_prompt(
            "Dazza", TRIGGER_BREAK_LIMIT,
            hours_driven_continuous=4.5,
            minutes_until_mandatory_break=15,
            next_rest_area_name="Southern Cross Truck Bay",
            next_rest_area_km=45,
        )
        assert "4.5 hours" in prompt
        assert "15 minutes" in prompt
        assert "Southern Cross" in prompt

    def test_companion_checkin_context(self):
        prompt = build_system_prompt("Dazza", TRIGGER_COMPANION_CHECK_IN)
        assert "friendly" in prompt.lower() or "check-in" in prompt.lower()

    def test_driver_initiated_inbound_flow(self):
        prompt = build_system_prompt("Dazza", TRIGGER_DRIVER_INITIATED)
        assert "driver is calling you" in prompt.lower() or "calling YOU" in prompt

    def test_outbound_call_flow(self):
        prompt = build_system_prompt("Dazza", TRIGGER_FATIGUE_CAMERA)
        assert "outbound call" in prompt.lower() or "Do NOT start talking" in prompt

    def test_memory_summary_injected(self):
        memory = "- 25 min ago: Driver was grumpy but agreed to take a break"
        prompt = build_system_prompt(
            "Dazza", "companion_check_in",
            memory_summary=memory,
        )
        assert "previous calls" in prompt.lower()
        assert "grumpy" in prompt

    def test_escalation_instruction_present(self):
        prompt = build_system_prompt("Dazza", "companion_check_in")
        assert "escalate" in prompt.lower()

    def test_escalation_announced_mode(self):
        prompt = build_system_prompt(
            "Dazza", "companion_check_in",
            escalation_mode="announced",
        )
        assert "let them know" in prompt.lower()

    def test_escalation_silent_mode(self):
        prompt = build_system_prompt(
            "Dazza", "companion_check_in",
            escalation_mode="silent",
        )
        assert "silently" in prompt

    def test_no_formatted_text_instruction(self):
        prompt = build_system_prompt("Dazza", "companion_check_in")
        assert "No formatted text" in prompt

    def test_mood_assessment_tool_mentioned(self):
        prompt = build_system_prompt("Dazza", "companion_check_in")
        assert "assess_driver_mood" in prompt

    def test_rest_stop_card_tool_mentioned(self):
        prompt = build_system_prompt("Dazza", "companion_check_in")
        assert "send_rest_stop_card" in prompt


class TestSpeaksFirstMessage:
    """Test speaks-first template retrieval."""

    def test_fatigue_camera(self):
        msg = get_speaks_first_message(TRIGGER_FATIGUE_CAMERA)
        assert "fatigue" in msg.lower() or "blip" in msg.lower()

    def test_erratic_driving(self):
        msg = get_speaks_first_message(TRIGGER_ERRATIC_DRIVING)
        assert "road" in msg.lower() or "driving" in msg.lower()

    def test_break_limit(self):
        msg = get_speaks_first_message(TRIGGER_BREAK_LIMIT)
        assert "rest" in msg.lower() or "break" in msg.lower()

    def test_companion_checkin(self):
        msg = get_speaks_first_message(TRIGGER_COMPANION_CHECK_IN)
        assert "check-in" in msg.lower() or "companion" in msg.lower()

    def test_driver_initiated(self):
        msg = get_speaks_first_message(TRIGGER_DRIVER_INITIATED)
        assert "calling" in msg.lower() or "hear from" in msg.lower()

    def test_unknown_trigger_fallback(self):
        msg = get_speaks_first_message("something_unknown")
        assert len(msg) > 10  # Returns a sensible fallback
