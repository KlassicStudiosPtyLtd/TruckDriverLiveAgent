"""Simulate a compressed 14-hour driver shift with random events.

Fires N random trigger events spread across a simulated shift,
running each simulated call sequentially with short delays between.
Progress is broadcast to the dashboard via WebSocket.
"""

import asyncio
import logging
import random
import time

from src.call.call_manager import CallManager
from src.call.simulated_call import run_simulated_call
from src.cards.wellness_card import generate_wellness_card
from src.data.mock_fleet import get_driver, update_driver_hours, get_driver_hours
from src.memory.store import clear_memory

logger = logging.getLogger(__name__)

SHIFT_DURATION_HOURS = 14.0
DELAY_BETWEEN_CALLS_S = 8  # real-time gap between calls

# Trigger templates with weights (more common events have higher weight)
TRIGGER_POOL = [
    # Fatigue camera events
    {"trigger_type": "fatigue_camera", "data": {"fatigue_event_type": "yawning", "severity": "low"}, "weight": 3, "min_hour": 1},
    {"trigger_type": "fatigue_camera", "data": {"fatigue_event_type": "droopy_eyes", "severity": "medium"}, "weight": 2, "min_hour": 3},
    {"trigger_type": "fatigue_camera", "data": {"fatigue_event_type": "head_nod", "severity": "high"}, "weight": 1, "min_hour": 8},
    {"trigger_type": "fatigue_camera", "data": {"fatigue_event_type": "distraction", "severity": "low"}, "weight": 2, "min_hour": 0},
    {"trigger_type": "fatigue_camera", "data": {"fatigue_event_type": "phone_use", "severity": "medium"}, "weight": 1, "min_hour": 0},
    {"trigger_type": "fatigue_camera", "data": {"fatigue_event_type": "smoking", "severity": "low"}, "weight": 1, "min_hour": 2},
    # Erratic driving events
    {"trigger_type": "erratic_driving", "data": {"erratic_sub_type": "lane_deviation"}, "weight": 2, "min_hour": 4},
    {"trigger_type": "erratic_driving", "data": {"erratic_sub_type": "harsh_braking", "g_force": 0.6}, "weight": 1, "min_hour": 2},
    {"trigger_type": "erratic_driving", "data": {"erratic_sub_type": "excessive_sway"}, "weight": 1, "min_hour": 3},
    {"trigger_type": "erratic_driving", "data": {"erratic_sub_type": "rollover_intervention", "g_force": 0.8}, "weight": 1, "min_hour": 6},
    # Other
    {"trigger_type": "break_limit", "data": {}, "weight": 2, "min_hour": 4},
    {"trigger_type": "companion_check_in", "data": {}, "weight": 3, "min_hour": 0},
    {"trigger_type": "driver_initiated", "data": {}, "weight": 2, "min_hour": 1},
]


def _pick_events(n: int) -> list[dict]:
    """Pick N events and assign them to realistic shift hours."""
    # Always start with a check-in and end with something serious
    events = []

    # First event: companion check-in early in shift
    events.append({
        "hour": round(random.uniform(0.5, 1.5), 1),
        "trigger_type": "companion_check_in",
        "data": {},
        "desc": "Start of shift check-in",
    })

    # Last event: high severity fatigue (if N > 2)
    if n > 2:
        last_hour = round(random.uniform(11.0, 13.5), 1)
        late_triggers = [t for t in TRIGGER_POOL
                         if t.get("data", {}).get("severity") == "high"
                         or t["trigger_type"] == "erratic_driving"]
        pick = random.choice(late_triggers)
        events.append({
            "hour": last_hour,
            "trigger_type": pick["trigger_type"],
            "data": dict(pick["data"]),
            "desc": f"Late shift: {pick['trigger_type']}",
        })

    # Fill middle slots
    middle_count = n - len(events)
    if middle_count > 0:
        # Generate evenly-spaced hours with jitter
        start_h = events[0]["hour"] + 1.5
        end_h = events[-1]["hour"] - 1.0 if len(events) > 1 else 12.0
        if end_h <= start_h:
            end_h = start_h + 2.0

        slot_hours = sorted([
            round(random.uniform(start_h, end_h), 1)
            for _ in range(middle_count)
        ])

        # Ensure minimum 1h gap between events
        for i in range(1, len(slot_hours)):
            if slot_hours[i] - slot_hours[i-1] < 1.0:
                slot_hours[i] = round(slot_hours[i-1] + 1.0, 1)

        for hour in slot_hours:
            eligible = [t for t in TRIGGER_POOL if t["min_hour"] <= hour]
            weights = [t["weight"] for t in eligible]
            pick = random.choices(eligible, weights=weights, k=1)[0]
            events.append({
                "hour": hour,
                "trigger_type": pick["trigger_type"],
                "data": dict(pick["data"]),
                "desc": f"{pick['trigger_type']} @ {hour}h",
            })

    events.sort(key=lambda e: e["hour"])
    return events


# Track active shift simulations
_active_shifts: dict[str, asyncio.Event] = {}


def is_shift_running(driver_id: str) -> bool:
    return driver_id in _active_shifts


def stop_shift(driver_id: str) -> bool:
    cancel = _active_shifts.get(driver_id)
    if cancel:
        cancel.set()
        return True
    return False


async def run_shift_simulation(
    driver_id: str,
    num_events: int,
    call_manager: CallManager,
    clear_memory_first: bool = True,
) -> dict:
    """Run a compressed shift simulation with random events."""
    driver = get_driver(driver_id)
    if not driver:
        return {"error": f"Unknown driver: {driver_id}"}

    if driver_id in _active_shifts:
        return {"error": "Shift simulation already running for this driver"}

    cancel_event = asyncio.Event()
    _active_shifts[driver_id] = cancel_event

    if clear_memory_first:
        clear_memory(driver_id)

    events = _pick_events(num_events)
    results = []
    t0 = time.time()

    try:
        await call_manager.broadcast_to_dashboard({
            "type": "shift_started",
            "driver_id": driver_id,
            "total_events": len(events),
            "schedule": [{"hour": e["hour"], "trigger": e["trigger_type"],
                          "desc": e["desc"]} for e in events],
        })

        for i, event in enumerate(events):
            if cancel_event.is_set():
                logger.info("Shift simulation cancelled for %s", driver_id)
                break

            # Update mock hours to match simulated shift position
            hour = event["hour"]
            update_driver_hours(
                driver_id,
                hours_driven_continuous=hour,
                minutes_until_mandatory_break=max(0, (5.0 - (hour % 5.0)) * 60),
            )

            await call_manager.broadcast_to_dashboard({
                "type": "shift_event",
                "driver_id": driver_id,
                "event_index": i + 1,
                "total_events": len(events),
                "hour": hour,
                "trigger_type": event["trigger_type"],
                "desc": event["desc"],
            })

            logger.info("Shift sim [%s] event %d/%d: %s @ %.1fh",
                         driver_id, i + 1, len(events),
                         event["trigger_type"], hour)

            result = await run_simulated_call(
                driver_id=driver_id,
                trigger_type=event["trigger_type"],
                trigger_data=event["data"],
                call_manager=call_manager,
            )

            results.append({
                "event": i + 1,
                "hour": hour,
                "trigger": event["trigger_type"],
                "desc": event["desc"],
                "status": result.get("status", "error"),
                "turns": result.get("turns", 0),
                "duration": result.get("duration", 0),
            })

            # Wait between calls (unless last or cancelled)
            if i < len(events) - 1 and not cancel_event.is_set():
                await asyncio.sleep(DELAY_BETWEEN_CALLS_S)

    except asyncio.CancelledError:
        logger.info("Shift simulation task cancelled for %s", driver_id)
    except Exception:
        logger.exception("Error in shift simulation for %s", driver_id)
    finally:
        _active_shifts.pop(driver_id, None)
        total_duration = round(time.time() - t0, 1)

        # Generate shift wellness summary card
        try:
            driver = get_driver(driver_id)
            driver_name = driver["first_name"] if driver else driver_id
            message = (
                f"Great effort today, {driver_name}. "
                f"{len(results)} check-ins across your shift — you handled them well. "
                f"Get some good rest tonight, mate."
            )
            card_url = generate_wellness_card(
                driver_id=driver_id,
                driver_name=driver_name,
                shift_results=results,
                total_duration_s=total_duration,
                message=message,
            )
            await call_manager.broadcast_to_dashboard({
                "type": "card",
                "card_type": "wellness_summary",
                "driver_id": driver_id,
                "image_url": card_url,
            })
        except Exception:
            logger.exception("Failed to generate wellness card for %s", driver_id)

        await call_manager.broadcast_to_dashboard({
            "type": "shift_ended",
            "driver_id": driver_id,
            "events_completed": len(results),
            "total_events": len(events),
            "duration_s": total_duration,
        })

        logger.info("Shift simulation ended for %s: %d/%d events in %.1fs",
                     driver_id, len(results), len(events), total_duration)

    return {
        "status": "completed" if len(results) == len(events) else "partial",
        "driver_id": driver_id,
        "events_completed": len(results),
        "total_events": len(events),
        "duration_s": round(time.time() - t0, 1),
        "results": results,
    }
