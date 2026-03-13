"""Unit tests for memory store — no API key needed."""

import os
import time
import pytest

os.environ["BETTY_MEMORY_KEY"] = "test-key-for-unit-tests-1234567890"

from src.memory.store import (
    add_entry, get_memory, get_memory_summary, clear_memory, clear_all, _get_db,
)


@pytest.fixture(autouse=True)
def clean_memory():
    """Clear all memory before each test."""
    clear_all()
    yield
    clear_all()


class TestMemoryStore:
    """Test memory persistence and retrieval."""

    def test_add_and_retrieve(self):
        add_entry("DRV-001", "Driver was tired", "fatigued", "encouraged_break")
        entries = get_memory("DRV-001")
        assert len(entries) == 1
        assert entries[0]["summary"] == "Driver was tired"
        assert entries[0]["fatigue_assessment"] == "fatigued"

    def test_multiple_entries(self):
        add_entry("DRV-001", "Call 1", "alert", "none")
        add_entry("DRV-001", "Call 2", "mildly_tired", "encouraged_break")
        entries = get_memory("DRV-001")
        assert len(entries) == 2

    def test_max_10_entries(self):
        for i in range(15):
            add_entry("DRV-001", f"Call {i}", "alert", "none")
        entries = get_memory("DRV-001")
        assert len(entries) == 10
        assert entries[0]["summary"] == "Call 5"  # Oldest 5 dropped

    def test_driver_isolation(self):
        add_entry("DRV-001", "Driver 1 data", "alert", "none")
        add_entry("DRV-002", "Driver 2 data", "fatigued", "escalated")
        entries1 = get_memory("DRV-001")
        entries2 = get_memory("DRV-002")
        assert len(entries1) == 1
        assert len(entries2) == 1
        assert entries1[0]["summary"] == "Driver 1 data"
        assert entries2[0]["summary"] == "Driver 2 data"

    def test_empty_memory_returns_empty_list(self):
        entries = get_memory("DRV-999")
        assert entries == []

    def test_clear_memory(self):
        add_entry("DRV-001", "Some data", "alert", "none")
        clear_memory("DRV-001")
        entries = get_memory("DRV-001")
        assert entries == []

    def test_clear_all(self):
        add_entry("DRV-001", "Data 1", "alert", "none")
        add_entry("DRV-002", "Data 2", "alert", "none")
        clear_all()
        assert get_memory("DRV-001") == []
        assert get_memory("DRV-002") == []

    def test_topics_stored(self):
        add_entry("DRV-001", "Talked about footy", "alert", "none",
                  topics=["footy", "family"])
        entries = get_memory("DRV-001")
        assert entries[0]["topics"] == ["footy", "family"]

    def test_timestamp_present(self):
        add_entry("DRV-001", "Test", "alert", "none")
        entries = get_memory("DRV-001")
        assert "timestamp" in entries[0]
        assert "T" in entries[0]["timestamp"]  # ISO format


class TestMemorySummary:
    """Test natural-language summary generation."""

    def test_no_memory_returns_none(self):
        summary = get_memory_summary("DRV-999")
        assert summary is None

    def test_summary_contains_entry_text(self):
        add_entry("DRV-001", "Driver was grumpy but agreed to stop", "fatigued",
                  "encouraged_break")
        summary = get_memory_summary("DRV-001")
        assert "grumpy" in summary
        assert "encouraged_break" in summary

    def test_summary_contains_time_reference(self):
        add_entry("DRV-001", "Recent call", "alert", "none")
        summary = get_memory_summary("DRV-001")
        assert "min ago" in summary or "h ago" in summary

    def test_summary_contains_topics(self):
        add_entry("DRV-001", "Chatted", "alert", "none",
                  topics=["footy", "family"])
        summary = get_memory_summary("DRV-001")
        assert "footy" in summary
        assert "family" in summary

    def test_multiple_entries_in_summary(self):
        add_entry("DRV-001", "First call", "alert", "none")
        add_entry("DRV-001", "Second call", "fatigued", "escalated")
        summary = get_memory_summary("DRV-001")
        assert "First call" in summary
        assert "Second call" in summary
