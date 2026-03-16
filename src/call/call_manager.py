"""Call lifecycle management — tracks pending and active calls."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class PendingCall:
    """A call waiting for a driver to accept."""

    def __init__(self, driver_id: str, trigger_type: str, trigger_data: dict,
                 driver_name_override: str = None):
        self.call_id = str(uuid.uuid4())[:8]
        self.driver_id = driver_id
        self.trigger_type = trigger_type
        self.trigger_data = trigger_data
        self.driver_name_override = driver_name_override
        self.created_at = datetime.now(timezone.utc)
        self.status = "pending"  # pending | ringing | connected | ended


class CallManager:
    """Manages call lifecycle: pending calls, driver WebSocket registrations."""

    def __init__(self):
        self._pending_calls: dict[str, PendingCall] = {}  # driver_id -> PendingCall
        self._active_calls: dict[str, PendingCall] = {}  # driver_id -> PendingCall
        self._last_transcripts: dict[str, list] = {}  # driver_id -> transcript entries
        self._notification_sockets: dict[str, WebSocket] = {}  # driver_id -> WS
        self._dashboard_sockets: list[WebSocket] = []

    def initiate_call(self, driver_id: str, trigger_type: str, trigger_data: dict,
                      driver_name_override: str = None) -> PendingCall:
        """Create a pending call for a driver."""
        call = PendingCall(driver_id, trigger_type, trigger_data, driver_name_override)
        self._pending_calls[driver_id] = call
        logger.info("Call initiated: %s for driver %s (trigger=%s)", call.call_id, driver_id, trigger_type)
        return call

    def get_pending_call(self, driver_id: str) -> Optional[PendingCall]:
        """Get the pending call for a driver, if any."""
        return self._pending_calls.get(driver_id)

    def accept_call(self, driver_id: str) -> Optional[PendingCall]:
        """Mark a pending call as connected."""
        call = self._pending_calls.pop(driver_id, None)
        if call:
            call.status = "connected"
            self._active_calls[driver_id] = call
            logger.info("Call accepted: %s for driver %s", call.call_id, driver_id)
        return call

    def end_call(self, driver_id: str) -> Optional[PendingCall]:
        """End an active call. Signals cancellation for simulated calls."""
        call = self._active_calls.pop(driver_id, None)
        if call:
            call.status = "ended"
            # Preserve transcript for polling after call ends
            transcript = getattr(call, "transcript", None)
            if transcript:
                self._last_transcripts[driver_id] = transcript
            # Signal cancellation to simulated call if running
            cancel = getattr(call, "cancel_event", None)
            if cancel:
                cancel.set()
            logger.info("Call ended: %s for driver %s", call.call_id, driver_id)
        return call

    def get_transcript(self, driver_id: str) -> tuple[list, str]:
        """Return transcript and status for a driver. Checks active then last."""
        call = self._active_calls.get(driver_id)
        if call and hasattr(call, "transcript"):
            return call.transcript, call.status
        # Check preserved transcript from ended call
        last = self._last_transcripts.get(driver_id)
        if last:
            return last, "ended"
        return [], "no_call"

    def get_active_call(self, driver_id: str) -> Optional[PendingCall]:
        """Get the active call for a driver."""
        return self._active_calls.get(driver_id)

    def get_all_active_calls(self) -> list[dict]:
        """Return all active calls as dicts for API responses."""
        result = []
        for call in self._active_calls.values():
            result.append({
                "call_id": call.call_id,
                "driver_id": call.driver_id,
                "trigger_type": call.trigger_type,
                "status": call.status,
                "created_at": call.created_at.isoformat(),
            })
        for call in self._pending_calls.values():
            result.append({
                "call_id": call.call_id,
                "driver_id": call.driver_id,
                "trigger_type": call.trigger_type,
                "status": "ringing",
                "created_at": call.created_at.isoformat(),
            })
        return result

    # --- Notification WebSocket management ---

    def register_notification_socket(self, driver_id: str, ws: WebSocket) -> None:
        self._notification_sockets[driver_id] = ws
        logger.info("Notification WS registered for driver %s", driver_id)

    def unregister_notification_socket(self, driver_id: str) -> None:
        self._notification_sockets.pop(driver_id, None)
        logger.info("Notification WS unregistered for driver %s", driver_id)

    async def notify_driver(self, driver_id: str, message: dict) -> bool:
        """Send a notification to a driver's browser via WebSocket."""
        ws = self._notification_sockets.get(driver_id)
        if ws:
            try:
                await ws.send_json(message)
                return True
            except Exception:
                logger.warning("Failed to notify driver %s", driver_id)
                self.unregister_notification_socket(driver_id)
        return False

    # --- Dashboard WebSocket management ---

    def register_dashboard_socket(self, ws: WebSocket) -> None:
        self._dashboard_sockets.append(ws)

    def unregister_dashboard_socket(self, ws: WebSocket) -> None:
        if ws in self._dashboard_sockets:
            self._dashboard_sockets.remove(ws)

    async def broadcast_to_dashboard(self, message: dict) -> None:
        """Send an update to all connected dashboards."""
        dead = []
        for ws in self._dashboard_sockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._dashboard_sockets.remove(ws)

    async def broadcast_audio_to_dashboard(self, pcm_data: bytes) -> None:
        """Send raw PCM audio bytes to all connected dashboards."""
        dead = []
        for ws in self._dashboard_sockets:
            try:
                await ws.send_bytes(pcm_data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._dashboard_sockets.remove(ws)
