"""Test all trigger combinations via simulated calls and verify transcripts."""

import asyncio
import json
import time
import sys
import os
import httpx

BASE = "http://localhost:8080"

# Rotate drivers to avoid conflicts on sequential tests using same driver
DRIVERS = ["DRV-001", "DRV-002", "DRV-003"]

TESTS = [
    # --- Fatigue Camera (all 6 event types) ---
    {
        "name": "fatigue / droopy_eyes / high",
        "payload": {
            "trigger_type": "fatigue_camera",
            "fatigue_event_type": "droopy_eyes",
            "severity": "high",
            "simulate": True,
        },
        "expect_keywords": ["tired", "rest", "break", "eye", "pull", "stop", "sleep"],
    },
    {
        "name": "fatigue / yawning / medium",
        "payload": {
            "trigger_type": "fatigue_camera",
            "fatigue_event_type": "yawning",
            "severity": "medium",
            "simulate": True,
        },
        "expect_keywords": ["tired", "yawn", "rest", "break", "feel"],
    },
    {
        "name": "fatigue / head_nod / high",
        "payload": {
            "trigger_type": "fatigue_camera",
            "fatigue_event_type": "head_nod",
            "severity": "high",
            "simulate": True,
        },
        "expect_keywords": ["tired", "rest", "break", "pull", "stop", "safe", "sleep"],
    },
    {
        "name": "fatigue / distraction / medium",
        "payload": {
            "trigger_type": "fatigue_camera",
            "fatigue_event_type": "distraction",
            "severity": "medium",
            "simulate": True,
        },
        "expect_keywords": ["focus", "distract", "alert", "road", "how", "feel"],
    },
    {
        "name": "fatigue / phone_use / medium",
        "payload": {
            "trigger_type": "fatigue_camera",
            "fatigue_event_type": "phone_use",
            "severity": "medium",
            "simulate": True,
        },
        "expect_keywords": ["phone", "road", "how", "check", "feel", "alert"],
    },
    {
        "name": "fatigue / smoking / low",
        "payload": {
            "trigger_type": "fatigue_camera",
            "fatigue_event_type": "smoking",
            "severity": "low",
            "simulate": True,
        },
        "expect_keywords": ["how", "going", "feel", "road", "check"],
    },
    # --- Erratic Driving (all 4 sub-types) ---
    {
        "name": "erratic / lane_deviation",
        "payload": {
            "trigger_type": "erratic_driving",
            "erratic_sub_type": "lane_deviation",
            "simulate": True,
        },
        "expect_keywords": ["road", "drift", "lane", "how", "alert", "drive"],
    },
    {
        "name": "erratic / harsh_braking",
        "payload": {
            "trigger_type": "erratic_driving",
            "erratic_sub_type": "harsh_braking",
            "simulate": True,
        },
        "expect_keywords": ["road", "brak", "okay", "how", "drive"],
    },
    {
        "name": "erratic / excessive_sway",
        "payload": {
            "trigger_type": "erratic_driving",
            "erratic_sub_type": "excessive_sway",
            "simulate": True,
        },
        "expect_keywords": ["sway", "road", "load", "how", "drive", "alert", "careful"],
    },
    {
        "name": "erratic / rollover_intervention",
        "payload": {
            "trigger_type": "erratic_driving",
            "erratic_sub_type": "rollover_intervention",
            "simulate": True,
        },
        "expect_keywords": ["pull", "stop", "safe", "over", "road", "how", "serious"],
    },
    # --- Other triggers ---
    {
        "name": "break_limit",
        "payload": {
            "trigger_type": "break_limit",
            "simulate": True,
        },
        "expect_keywords": ["break", "rest", "stop", "hour", "drive", "pull"],
    },
    {
        "name": "companion_check_in",
        "payload": {
            "trigger_type": "companion_check_in",
            "simulate": True,
        },
        "expect_keywords": ["how", "going", "check", "doing", "hey", "g'day"],
    },
]


async def wait_for_call_end(client: httpx.AsyncClient, driver_id: str, timeout: int = 90) -> list:
    """Poll until the call ends, then return the transcript."""
    start = time.time()
    saw_connected = False
    while time.time() - start < timeout:
        resp = await client.get(f"{BASE}/dashboard/api/transcript/{driver_id}")
        data = resp.json()

        if data["status"] == "connected":
            saw_connected = True

        if data["status"] == "ended" and data["transcript"]:
            return data["transcript"]

        if saw_connected:
            status_resp = await client.get(f"{BASE}/dashboard/api/status")
            status = status_resp.json()
            active = [c for c in status["active_calls"] if c["driver_id"] == driver_id]
            if not active:
                resp = await client.get(f"{BASE}/dashboard/api/transcript/{driver_id}")
                return resp.json().get("transcript", [])

        await asyncio.sleep(2)
    return []


async def run_test(client: httpx.AsyncClient, test: dict, driver_id: str) -> dict:
    """Run a single trigger test and return results."""
    name = test["name"]
    payload = {**test["payload"], "driver_id": driver_id}
    keywords = test["expect_keywords"]

    print(f"\n{'='*60}")
    print(f"  TEST: {name}")
    print(f"  Driver: {driver_id}")
    print(f"{'='*60}")

    resp = await client.post(f"{BASE}/api/triggers/trigger", json=payload)
    if resp.status_code != 200:
        return {"name": name, "status": "FAIL", "error": f"Trigger failed: {resp.text}"}

    transcript = await wait_for_call_end(client, driver_id)

    if not transcript:
        return {"name": name, "status": "FAIL", "error": "No transcript captured"}

    full_text = " ".join(e["text"] for e in transcript).lower()

    # Print consolidated transcript
    current_speaker = None
    line = ""
    for entry in transcript:
        if entry["speaker"] != current_speaker:
            if line:
                print(f"  [{current_speaker}]: {line.strip()}")
            current_speaker = entry["speaker"]
            line = entry["text"]
        else:
            line += " " + entry["text"]
    if line:
        print(f"  [{current_speaker}]: {line.strip()}")

    found = [kw for kw in keywords if kw.lower() in full_text]
    missing = [kw for kw in keywords if kw.lower() not in full_text]

    status = "PASS" if len(found) >= 2 else "WEAK"
    print(f"\n  Keywords found: {found}")
    if missing:
        print(f"  Keywords missing: {missing}")
    print(f"  Result: {status}")

    return {
        "name": name,
        "status": status,
        "found_keywords": found,
        "missing_keywords": missing,
        "transcript_lines": len(transcript),
    }


async def main():
    results = []
    async with httpx.AsyncClient(timeout=120) as client:
        for i, test in enumerate(TESTS):
            if results:
                await asyncio.sleep(3)
            driver_id = DRIVERS[i % len(DRIVERS)]
            result = await run_test(client, test, driver_id)
            results.append(result)

    print(f"\n\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for r in results:
        icon = "OK" if r["status"] == "PASS" else "??" if r["status"] == "WEAK" else "XX"
        print(f"  [{icon}] {r['name']}: {r['status']}")
        if r.get("error"):
            print(f"       Error: {r['error']}")
    print(f"{'='*60}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    weak = sum(1 for r in results if r["status"] == "WEAK")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"  PASS: {passed} | WEAK: {weak} | FAIL: {failed} / {len(results)} total")


if __name__ == "__main__":
    asyncio.run(main())
