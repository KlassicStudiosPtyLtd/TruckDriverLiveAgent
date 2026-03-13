"""Unit tests for video frame path resolution — no API key needed.

Note: actual frame extraction requires cv2 + video files.
These tests cover the path resolution logic only.
"""

import pytest
from unittest.mock import patch

from src.call.video_frames import _resolve_video_path, _VIDEO_MAP, DRIVER_VIDEO_MAP


class TestVideoPathResolution:
    """Test video file path resolution logic."""

    @patch("os.path.exists", return_value=True)
    def test_exact_match(self, mock_exists):
        path = _resolve_video_path("droopy_eyes", "high", "DRV-001")
        assert path is not None
        assert "fatigue_droopy_eyes_high.mp4" in path

    @patch("os.path.exists", return_value=True)
    def test_fallback_to_none_severity(self, mock_exists):
        path = _resolve_video_path("head_nod", "low", "DRV-001")
        assert path is not None
        assert "fatigue_head_nod.mp4" in path

    @patch("os.path.exists", return_value=True)
    def test_erratic_events(self, mock_exists):
        path = _resolve_video_path("lane_deviation", None, "DRV-001")
        assert path is not None
        assert "erratic_lane_deviation.mp4" in path

    def test_unknown_event_returns_none(self):
        path = _resolve_video_path("totally_unknown_event", None, "DRV-001")
        assert path is None

    def test_video_map_coverage(self):
        """Verify all expected event types have video mappings."""
        fatigue_types = ["droopy_eyes", "yawning", "head_nod", "distraction",
                         "phone_use", "smoking"]
        erratic_types = ["lane_deviation", "harsh_braking", "excessive_sway",
                         "rollover_intervention"]

        mapped_events = set(k[0] for k in _VIDEO_MAP.keys())
        for et in fatigue_types + erratic_types:
            assert et in mapped_events, f"Missing video mapping for: {et}"

    def test_driver_video_map(self):
        """Verify all drivers have video folder mappings."""
        for driver_id in ["DRV-001", "DRV-002", "DRV-003"]:
            assert driver_id in DRIVER_VIDEO_MAP
