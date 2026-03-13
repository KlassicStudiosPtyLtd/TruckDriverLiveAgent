"""Unit tests for call lifecycle management — no API key needed."""

import asyncio
import pytest

from src.call.call_manager import CallManager, PendingCall


@pytest.fixture
def cm():
    return CallManager()


class TestCallLifecycle:
    """Test call state transitions."""

    def test_initiate_call(self, cm):
        call = cm.initiate_call("DRV-001", "fatigue_camera", {"severity": "high"})
        assert call.driver_id == "DRV-001"
        assert call.trigger_type == "fatigue_camera"
        assert call.status == "pending"
        assert len(call.call_id) == 8

    def test_accept_call(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        call = cm.accept_call("DRV-001")
        assert call is not None
        assert call.status == "connected"

    def test_accept_removes_from_pending(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        cm.accept_call("DRV-001")
        assert cm.get_pending_call("DRV-001") is None

    def test_accept_adds_to_active(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        cm.accept_call("DRV-001")
        assert cm.get_active_call("DRV-001") is not None

    def test_end_call(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        cm.accept_call("DRV-001")
        call = cm.end_call("DRV-001")
        assert call is not None
        assert call.status == "ended"

    def test_end_removes_from_active(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        cm.accept_call("DRV-001")
        cm.end_call("DRV-001")
        assert cm.get_active_call("DRV-001") is None

    def test_accept_nonexistent_returns_none(self, cm):
        assert cm.accept_call("DRV-999") is None

    def test_end_nonexistent_returns_none(self, cm):
        assert cm.end_call("DRV-999") is None


class TestMultipleDrivers:
    """Test concurrent calls for different drivers."""

    def test_independent_calls(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        cm.initiate_call("DRV-002", "erratic_driving", {})
        assert cm.get_pending_call("DRV-001") is not None
        assert cm.get_pending_call("DRV-002") is not None

    def test_accept_one_doesnt_affect_other(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        cm.initiate_call("DRV-002", "erratic_driving", {})
        cm.accept_call("DRV-001")
        assert cm.get_pending_call("DRV-002") is not None
        assert cm.get_active_call("DRV-001") is not None


class TestGetAllActiveCalls:
    """Test active call listing."""

    def test_empty_initially(self, cm):
        assert cm.get_all_active_calls() == []

    def test_includes_pending(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        calls = cm.get_all_active_calls()
        assert len(calls) == 1
        assert calls[0]["status"] == "ringing"

    def test_includes_connected(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        cm.accept_call("DRV-001")
        calls = cm.get_all_active_calls()
        assert len(calls) == 1
        assert calls[0]["status"] == "connected"

    def test_ended_not_included(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        cm.accept_call("DRV-001")
        cm.end_call("DRV-001")
        assert cm.get_all_active_calls() == []


class TestTranscript:
    """Test transcript retrieval."""

    def test_no_transcript(self, cm):
        transcript, status = cm.get_transcript("DRV-001")
        assert transcript == []
        assert status == "no_call"

    def test_transcript_preserved_after_end(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        call = cm.accept_call("DRV-001")
        call.transcript = [{"speaker": "Betty", "text": "G'day!"}]
        cm.end_call("DRV-001")
        transcript, status = cm.get_transcript("DRV-001")
        assert len(transcript) == 1
        assert status == "ended"


class TestCancelEvent:
    """Test cancel event signaling for simulated calls."""

    def test_cancel_event_set_on_end(self, cm):
        cm.initiate_call("DRV-001", "fatigue_camera", {})
        call = cm.accept_call("DRV-001")
        cancel = asyncio.Event()
        call.cancel_event = cancel
        cm.end_call("DRV-001")
        assert cancel.is_set()
