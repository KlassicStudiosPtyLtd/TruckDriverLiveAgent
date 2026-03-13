"""Extract frames from fatigue camera videos for Gemini Live API injection.

Extracts key frames from MP4 files at ~1 fps and encodes as JPEG bytes
for sending via send_realtime_input(video=...).

Videos are organised by driver name in subfolders:
  data/mock/videos/dazza/
  data/mock/videos/shazza/   (future)
  data/mock/videos/macca/    (future)
"""

import logging
import os
from typing import Optional

import cv2

logger = logging.getLogger(__name__)

VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "mock", "videos")

# Default driver for video lookup (until per-driver videos are generated)
DEFAULT_DRIVER = "dazza"

# Map driver_id -> video subfolder name
DRIVER_VIDEO_MAP = {
    "DRV-001": "dazza",
    "DRV-002": "dazza",  # TODO: generate shazza videos
    "DRV-003": "dazza",  # TODO: generate macca videos
}

# Map (event_type, severity) -> video filename
# Some events have severity variants, others don't
_VIDEO_MAP = {
    ("droopy_eyes", "low"): "fatigue_droopy_eyes_low.mp4",
    ("droopy_eyes", "medium"): "fatigue_droopy_eyes_low.mp4",
    ("droopy_eyes", "high"): "fatigue_droopy_eyes_high.mp4",
    ("yawning", "low"): "fatigue_yawning_low.mp4",
    ("yawning", "medium"): "fatigue_yawning_low.mp4",
    ("yawning", "high"): "fatigue_yawning_high.mp4",
    ("head_nod", None): "fatigue_head_nod.mp4",
    ("distraction", None): "fatigue_distraction.mp4",
    ("phone_use", None): "fatigue_phone_use.mp4",
    ("smoking", None): "fatigue_smoking.mp4",
    ("lane_deviation", None): "erratic_lane_deviation.mp4",
    ("harsh_braking", None): "erratic_harsh_braking.mp4",
    ("excessive_sway", None): "erratic_excessive_sway.mp4",
    ("rollover_intervention", None): "erratic_rollover_intervention.mp4",
}


def _resolve_video_path(event_type: str, severity: Optional[str] = None,
                        driver_id: Optional[str] = None) -> Optional[str]:
    """Find the video file for a given event type, severity, and driver."""
    # Determine which driver subfolder to use
    driver_folder = DRIVER_VIDEO_MAP.get(driver_id, DEFAULT_DRIVER) if driver_id else DEFAULT_DRIVER

    # Try exact match first
    filename = _VIDEO_MAP.get((event_type, severity))
    if not filename:
        filename = _VIDEO_MAP.get((event_type, None))
    if not filename:
        filename = _VIDEO_MAP.get((event_type, "medium"))
    if not filename:
        return None

    full_path = os.path.join(VIDEOS_DIR, driver_folder, filename)
    if not os.path.exists(full_path):
        # Fall back to default driver
        if driver_folder != DEFAULT_DRIVER:
            full_path = os.path.join(VIDEOS_DIR, DEFAULT_DRIVER, filename)
        if not os.path.exists(full_path):
            logger.warning("Video file not found: %s", full_path)
            return None
    return full_path


def extract_frames(event_type: str, severity: Optional[str] = None,
                   target_fps: float = 1.0,
                   driver_id: Optional[str] = None) -> list[bytes]:
    """Extract JPEG frames from a fatigue event video.

    Args:
        event_type: Fatigue event type (droopy_eyes, yawning, etc.)
        severity: Severity level (low, medium, high)
        target_fps: Target frame rate for extraction (default 1 fps)
        driver_id: Driver ID for per-driver video selection

    Returns:
        List of JPEG-encoded frame bytes
    """
    video_path = _resolve_video_path(event_type, severity, driver_id)
    if not video_path:
        logger.warning("No video found for event_type=%s severity=%s driver=%s",
                       event_type, severity, driver_id)
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Failed to open video: %s", video_path)
        return []

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = max(1, int(video_fps / target_fps))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    logger.info("Extracting frames from %s (%.0f fps, %d total, interval=%d)",
                os.path.basename(video_path), video_fps, total_frames, frame_interval)

    frames = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            # Resize to 640px wide for reasonable payload size
            h, w = frame.shape[:2]
            if w > 640:
                scale = 640 / w
                frame = cv2.resize(frame, (640, int(h * scale)))

            _, jpeg_bytes = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frames.append(jpeg_bytes.tobytes())
        frame_idx += 1

    cap.release()
    logger.info("Extracted %d frames from %s", len(frames), os.path.basename(video_path))
    return frames
