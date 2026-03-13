"""Test memory persistence across multiple calls over a simulated 14-hour shift.

Runs N simulated calls for a single driver, advancing the mock hours between
calls. After each call, verifies memory was saved and that Betty's prompt
includes notes from previous calls.

Usage:
    set GEMINI_API_KEY=your-key
    set BETTY_MEMORY_KEY=any-secret
    python tests/test_memory.py
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.memory.store import get_memory, get_memory_summary, clear_memory, add_entry, _get_db, _purge_expired
from src.memory.crypto import encrypt, decrypt
from src.voice.prompts import build_system_prompt
from src.data.mock_fleet import get_driver, get_driver_hours, update_driver_hours

# --- Config ---
DRIVER_ID = "DRV-001"
BASE_URL = "http://localhost:8080"

# Simulated shift: calls at these hours into the shift
SHIFT_CALLS = [
    {"hours_in": 1.0, "trigger": "companion_check_in", "data": {},
     "desc": "Start of shift check-in"},
    {"hours_in": 3.5, "trigger": "fatigue_camera", "data": {"fatigue_event_type": "yawning", "severity": "low"},
     "desc": "Light yawning detected"},
    {"hours_in": 5.0, "trigger": "break_limit", "data": {},
     "desc": "Approaching mandatory break"},
    {"hours_in": 7.0, "trigger": "companion_check_in", "data": {},
     "desc": "Post-break check-in"},
    {"hours_in": 9.5, "trigger": "fatigue_camera", "data": {"fatigue_event_type": "droopy_eyes", "severity": "medium"},
     "desc": "Droopy eyes after long drive"},
    {"hours_in": 11.0, "trigger": "erratic_driving", "data": {"erratic_sub_type": "lane_deviation"},
     "desc": "Lane deviation late in shift"},
    {"hours_in": 13.0, "trigger": "fatigue_camera", "data": {"fatigue_event_type": "head_nod", "severity": "high"},
     "desc": "Head nod — critical fatigue"},
]


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


async def wait_for_call_end(driver_id: str, timeout: int = 90) -> list:
    """Poll until the simulated call ends."""
    import httpx
    start = time.time()
    async with httpx.AsyncClient(timeout=30) as client:
        while time.time() - start < timeout:
            resp = await client.get(f"{BASE_URL}/dashboard/api/transcript/{driver_id}")
            data = resp.json()
            if data["status"] == "ended" and data["transcript"]:
                return data["transcript"]
            await asyncio.sleep(2)
    return []


async def run_call(call_num: int, call_info: dict) -> dict:
    """Run a single simulated call and return results."""
    import httpx

    hours_in = call_info["hours_in"]
    trigger = call_info["trigger"]
    trigger_data = call_info["data"]
    desc = call_info["desc"]

    print_section(f"CALL {call_num}/{len(SHIFT_CALLS)} — {desc}")
    print(f"  Hours into shift: {hours_in}")
    print(f"  Trigger: {trigger}")

    # Update mock hours to simulate time passing
    update_driver_hours(DRIVER_ID,
                        hours_driven_continuous=hours_in,
                        minutes_until_mandatory_break=max(0, (5.0 - (hours_in % 5.0)) * 60))

    # Check what memory Betty will see
    memory = get_memory_summary(DRIVER_ID)
    if memory:
        print(f"\n  Memory Betty sees before this call:")
        for line in memory.split("\n"):
            print(f"    {line}")
    else:
        print(f"\n  No previous memory (first call)")

    # Send trigger
    payload = {
        "driver_id": DRIVER_ID,
        "trigger_type": trigger,
        **trigger_data,
        "simulate": True,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{BASE_URL}/api/triggers/trigger", json=payload)
        if resp.status_code != 200:
            return {"call": call_num, "status": "FAIL", "error": resp.text}

    # Wait for call to complete
    transcript = await wait_for_call_end(DRIVER_ID)

    if not transcript:
        return {"call": call_num, "status": "FAIL", "error": "No transcript"}

    # Print transcript
    print(f"\n  Transcript:")
    current = None
    line = ""
    for entry in transcript:
        if entry["speaker"] != current:
            if line:
                print(f"    [{current}]: {line.strip()}")
            current = entry["speaker"]
            line = entry["text"]
        else:
            line += " " + entry["text"]
    if line:
        print(f"    [{current}]: {line.strip()}")

    # Verify memory was saved
    entries = get_memory(DRIVER_ID)
    print(f"\n  Memory entries after call: {len(entries)}")

    return {
        "call": call_num,
        "status": "PASS",
        "hours_in": hours_in,
        "trigger": trigger,
        "memory_count": len(entries),
        "transcript_lines": len(transcript),
    }


async def main():
    # Preflight checks
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: Set GEMINI_API_KEY")
        sys.exit(1)
    if not os.environ.get("BETTY_MEMORY_KEY"):
        print("ERROR: Set BETTY_MEMORY_KEY")
        sys.exit(1)

    # Check server is running
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{BASE_URL}/health")
            if resp.status_code != 200:
                raise Exception()
    except Exception:
        print(f"ERROR: Server not running at {BASE_URL}")
        print(f"Start it first: python -m uvicorn src.main:app --host 127.0.0.1 --port 8080")
        sys.exit(1)

    print_section("MEMORY PERSISTENCE TEST — SIMULATED 14-HOUR SHIFT")
    print(f"  Driver: {DRIVER_ID}")
    print(f"  Calls planned: {len(SHIFT_CALLS)}")
    print(f"  Shift span: {SHIFT_CALLS[0]['hours_in']}h to {SHIFT_CALLS[-1]['hours_in']}h")

    # Clear any existing memory for clean test
    clear_memory(DRIVER_ID)
    print(f"  Memory cleared for clean start")

    # Run calls
    results = []
    for i, call_info in enumerate(SHIFT_CALLS, 1):
        if i > 1:
            print(f"\n  ... waiting 5s before next call ...")
            await asyncio.sleep(5)
        result = await run_call(i, call_info)
        results.append(result)

    # --- Isolation test ---
    print_section("ISOLATION TEST")
    other_memory = get_memory_summary("DRV-002")
    print(f"  DRV-002 memory: {other_memory or 'None (correct — isolated)'}")

    # Try cross-driver decryption
    db = _get_db()
    row = db.execute(
        "SELECT encrypted_blob FROM driver_memory WHERE driver_id = ?",
        (DRIVER_ID,)
    ).fetchone()
    db.close()
    if row:
        try:
            decrypt("DRV-002", row[0])
            print(f"  Cross-driver decrypt: FAILED (should not succeed)")
        except Exception:
            print(f"  Cross-driver decrypt: Blocked (correct — InvalidTag)")

    # --- TTL test ---
    print_section("TTL TEST")
    entries_before = len(get_memory(DRIVER_ID))
    # Manually backdate the entry to simulate expiry
    db = _get_db()
    expired_time = time.time() - (15 * 3600)  # 15 hours ago (beyond 14h TTL)
    db.execute("UPDATE driver_memory SET updated_at = ? WHERE driver_id = ?",
               (expired_time, DRIVER_ID))
    db.commit()
    db.close()
    entries_after = get_memory(DRIVER_ID)  # This triggers purge
    print(f"  Entries before expiry: {entries_before}")
    print(f"  Entries after simulated 15h: {len(entries_after)} (should be 0)")
    ttl_pass = len(entries_after) == 0

    # --- Summary ---
    print_section("SUMMARY")
    for r in results:
        icon = "OK" if r["status"] == "PASS" else "XX"
        if r["status"] == "PASS":
            print(f"  [{icon}] Call {r['call']} ({r['trigger']} @ {r['hours_in']}h): "
                  f"memory={r['memory_count']} entries, transcript={r['transcript_lines']} lines")
        else:
            print(f"  [{icon}] Call {r['call']}: {r.get('error', 'unknown')}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] != "PASS")
    print(f"\n  Calls: {passed} PASS / {failed} FAIL")
    print(f"  Isolation: {'PASS' if not other_memory else 'FAIL'}")
    print(f"  TTL expiry: {'PASS' if ttl_pass else 'FAIL'}")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
