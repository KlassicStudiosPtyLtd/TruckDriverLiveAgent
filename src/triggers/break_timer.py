"""Periodic break limit checker — runs in background, checks all drivers."""

import asyncio
import logging
from typing import Callable, Optional

from src.data.mock_fleet import check_break_limit, get_all_drivers

logger = logging.getLogger(__name__)


class BreakTimer:
    """Periodically checks all drivers' hours and triggers alerts when approaching break limits."""

    def __init__(
        self,
        on_break_alert: Callable,
        interval_minutes: int = 15,
        warning_threshold_minutes: int = 30,
    ):
        self.on_break_alert = on_break_alert
        self.interval_minutes = interval_minutes
        self.warning_threshold = warning_threshold_minutes
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the periodic break limit checker."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Break timer started (interval: %d min, threshold: %d min)",
                     self.interval_minutes, self.warning_threshold)

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Break timer stopped")

    async def _run_loop(self) -> None:
        """Main loop that periodically checks all drivers."""
        while self._running:
            try:
                await self._check_all_drivers()
            except Exception:
                logger.exception("Error in break timer check")
            await asyncio.sleep(self.interval_minutes * 60)

    async def _check_all_drivers(self) -> None:
        """Check all drivers for approaching break limits."""
        drivers = get_all_drivers()
        for driver in drivers:
            event = check_break_limit(driver["driver_id"], self.warning_threshold)
            if event:
                logger.info(
                    "Break limit alert: %s has %d min until mandatory break",
                    driver["driver_id"], event["minutes_until_mandatory_break"],
                )
                await self.on_break_alert(driver["driver_id"], event)

    async def check_single_driver(self, driver_id: str) -> Optional[dict]:
        """Manually check a single driver's break status."""
        return check_break_limit(driver_id, self.warning_threshold)
