"""Unit tests for config parsing — no API key needed."""

import os
import yaml
import pytest

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "betty.yaml")


class TestConfigStructure:
    """Verify config file is valid and has required sections."""

    @pytest.fixture(autouse=True)
    def load_config(self):
        with open(CONFIG_PATH, "r") as f:
            self.config = yaml.safe_load(f)

    def test_config_loads(self):
        assert self.config is not None

    def test_betty_section(self):
        assert "betty" in self.config

    def test_personality(self):
        p = self.config["betty"]["personality"]
        assert p["name"] == "Betty"
        assert p["voice"] == "Aoede"
        assert p["greeting_style"] in ("warm", "professional", "casual")

    def test_memory_config(self):
        m = self.config["betty"]["memory"]
        assert m["cross_call_memory"] is True
        assert m["memory_duration_hours"] == 14

    def test_escalation_config(self):
        e = self.config["betty"]["escalation"]
        assert e["mode"] in ("announced", "silent")
        assert isinstance(e["fatigue_refusal_threshold_minutes"], int)
        assert isinstance(e["consecutive_events_threshold"], int)

    def test_break_alerts(self):
        b = self.config["betty"]["break_alerts"]
        assert b["warning_threshold_minutes"] > 0
        assert b["reminder_interval_minutes"] > 0

    def test_call_config(self):
        c = self.config["betty"]["call"]
        assert c["max_call_duration_minutes"] > 0
        assert c["ring_timeout_seconds"] > 0

    def test_triggers_config(self):
        t = self.config["betty"]["triggers"]
        assert isinstance(t["fatigue_low_auto_call"], bool)
        assert isinstance(t["erratic_driving_auto_call"], bool)

    def test_google_config(self):
        g = self.config["google"]["gemini"]
        assert "model" in g
        assert g["api_key_env"] == "GEMINI_API_KEY"

    def test_server_config(self):
        s = self.config["server"]
        assert isinstance(s["port"], int)
        assert s["host"] == "0.0.0.0"
