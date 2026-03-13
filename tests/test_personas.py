"""Test 20 persona combinations with Betty.

Runs simulated calls across all 3 drivers with varied mood/situation/resistance
combos. Evaluates whether Betty adapts her tone appropriately.

Usage:
    set GEMINI_API_KEY=your-key
    set BETTY_MEMORY_KEY=any-secret
    python tests/test_personas.py
"""

import asyncio
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = "http://localhost:8080"

# All trigger types to cycle through
TRIGGERS = [
    {"trigger_type": "fatigue_camera", "fatigue_event_type": "yawning", "severity": "medium"},
    {"trigger_type": "fatigue_camera", "fatigue_event_type": "droopy_eyes", "severity": "high"},
    {"trigger_type": "fatigue_camera", "fatigue_event_type": "head_nod", "severity": "high"},
    {"trigger_type": "erratic_driving", "erratic_sub_type": "lane_deviation"},
    {"trigger_type": "erratic_driving", "erratic_sub_type": "harsh_braking", "g_force": 0.7},
    {"trigger_type": "break_limit"},
    {"trigger_type": "companion_check_in"},
    {"trigger_type": "driver_initiated"},
]

DRIVERS = ["DRV-001", "DRV-002", "DRV-003"]


def build_test_matrix(n: int) -> list[dict]:
    """Build N test cases from persona combinations x triggers x drivers."""
    import httpx

    # Load personas from server
    resp = httpx.get(f"{BASE_URL}/api/personas", timeout=5)
    personas = resp.json()

    moods = list(personas["moods"].keys())
    situations = list(personas["situations"].keys())
    resistances = list(personas["resistance_levels"].keys())
    presets = personas.get("preset_combinations", [])

    tests = []

    # First 10: use the named presets
    for i, preset in enumerate(presets[:min(n, len(presets))]):
        trigger = TRIGGERS[i % len(TRIGGERS)]
        driver = DRIVERS[i % len(DRIVERS)]
        tests.append({
            "name": preset["name"],
            "driver_id": driver,
            "persona_mood": preset["mood"],
            "persona_situation": preset["situation"],
            "persona_resistance": preset["resistance"],
            **trigger,
        })

    # Remaining: random combos
    while len(tests) < n:
        trigger = random.choice(TRIGGERS)
        tests.append({
            "name": f"Random #{len(tests) + 1}",
            "driver_id": random.choice(DRIVERS),
            "persona_mood": random.choice(moods),
            "persona_situation": random.choice(situations),
            "persona_resistance": random.choice(resistances),
            **trigger,
        })

    return tests


# --- Evaluation keywords ---
# Map mood/situation to words we'd expect from the driver or Betty's adaptation

DRIVER_KEYWORDS = {
    "grumpy": ["nah", "whatever", "fine", "leave me", "don't"],
    "anxious": ["worried", "late", "behind", "stress", "scared", "nervous"],
    "lonely": ["miss", "family", "kids", "alone", "chat", "talk"],
    "stressed": ["boss", "late", "pressure", "deadline", "bloody"],
    "homesick": ["miss", "family", "kids", "wife", "husband", "home", "dog"],
    "exhausted": ["tired", "knackered", "sleep", "heavy", "can't"],
    "cocky": ["years", "done this", "know what", "fine", "thousand"],
    "new_driver": ["first", "new", "not sure", "advice", "nervous"],
    "cheerful": ["good", "great", "love", "beautiful", "ripper", "awesome"],
    "stoic": [],  # stoic is about brevity, not keywords
}

BETTY_ADAPTATION_KEYWORDS = {
    "grumpy": ["understand", "won't push", "no worries", "fair enough"],
    "anxious": ["calm", "safe", "okay", "alright", "no rush", "don't worry"],
    "lonely": ["chat", "here for you", "tell me", "how's", "talk"],
    "stressed": ["understand", "tough", "pressure", "take it easy"],
    "exhausted": ["break", "stop", "rest", "pull over", "worried", "safety"],
    "defiant": ["understand", "respect", "just", "concerned"],
}

SITUATION_KEYWORDS = {
    "running_late": ["late", "time", "behind", "schedule", "delivery"],
    "bad_weather": ["rain", "weather", "wet", "wind", "storm", "visibility"],
    "near_miss": ["close", "scare", "nearly", "car", "roo", "swerve", "heart"],
    "radio_broke": ["radio", "music", "quiet", "boring", "silence"],
    "argument_dispatch": ["dispatch", "boss", "told", "route", "angry", "blue"],
    "bad_sleep": ["sleep", "night", "rest", "tired", "tossed"],
    "beautiful_drive": ["beautiful", "sunset", "sunrise", "view", "sky", "stunning"],
    "mechanical_issue": ["noise", "engine", "brake", "light", "warning", "feel"],
}


def evaluate_transcript(test: dict, transcript: list[dict]) -> dict:
    """Score how well the conversation matched the persona."""
    if not transcript:
        return {"score": 0, "notes": "No transcript"}

    driver_text = " ".join(
        e["text"].lower() for e in transcript if e["speaker"] != "betty"
    )
    betty_text = " ".join(
        e["text"].lower() for e in transcript if e["speaker"] == "betty"
    )
    all_text = driver_text + " " + betty_text

    notes = []
    score = 0
    max_score = 0

    mood = test.get("persona_mood", "")
    situation = test.get("persona_situation", "")
    resistance = test.get("persona_resistance", "")

    # Check driver mood keywords
    if mood in DRIVER_KEYWORDS and DRIVER_KEYWORDS[mood]:
        max_score += 2
        hits = [kw for kw in DRIVER_KEYWORDS[mood] if kw in driver_text]
        if hits:
            score += 2
            notes.append(f"Mood '{mood}' detected: {', '.join(hits[:3])}")
        else:
            notes.append(f"Mood '{mood}' keywords not found in driver speech")

    # Check situation keywords
    if situation in SITUATION_KEYWORDS:
        max_score += 2
        hits = [kw for kw in SITUATION_KEYWORDS[situation] if kw in all_text]
        if hits:
            score += 2
            notes.append(f"Situation '{situation}' detected: {', '.join(hits[:3])}")
        else:
            notes.append(f"Situation '{situation}' keywords not found")

    # Check Betty adaptation
    if mood in BETTY_ADAPTATION_KEYWORDS:
        max_score += 2
        hits = [kw for kw in BETTY_ADAPTATION_KEYWORDS[mood] if kw in betty_text]
        if hits:
            score += 2
            notes.append(f"Betty adapted to '{mood}': {', '.join(hits[:3])}")
        else:
            notes.append(f"Betty didn't show clear adaptation to '{mood}'")

    # Check resistance behaviour
    if resistance == "defiant":
        max_score += 2
        # Defiant drivers should refuse suggestions
        refusal_kw = ["no", "nah", "won't", "don't tell", "fine", "not stopping"]
        hits = [kw for kw in refusal_kw if kw in driver_text]
        if hits:
            score += 2
            notes.append(f"Defiant resistance shown: {', '.join(hits[:3])}")
        else:
            notes.append("Defiant resistance not clearly shown")
    elif resistance == "cooperative":
        max_score += 2
        coop_kw = ["yeah", "right", "okay", "will do", "good idea", "probably"]
        hits = [kw for kw in coop_kw if kw in driver_text]
        if hits:
            score += 2
            notes.append(f"Cooperative shown: {', '.join(hits[:3])}")
        else:
            notes.append("Cooperative behaviour not clearly shown")

    # Check conversation happened at all (baseline)
    max_score += 1
    driver_lines = [e for e in transcript if e["speaker"] != "betty"]
    betty_lines = [e for e in transcript if e["speaker"] == "betty"]
    if len(driver_lines) >= 2 and len(betty_lines) >= 2:
        score += 1
        notes.append(f"Conversation: {len(driver_lines)} driver, {len(betty_lines)} Betty lines")
    else:
        notes.append(f"Short conversation: {len(driver_lines)} driver, {len(betty_lines)} Betty")

    pct = round(score / max_score * 100) if max_score > 0 else 0

    return {
        "score": score,
        "max_score": max_score,
        "pct": pct,
        "notes": notes,
    }


def print_section(title: str):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


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


async def run_test(i: int, total: int, test: dict) -> dict:
    """Run a single persona test."""
    import httpx

    driver_id = test["driver_id"]
    trigger_type = test["trigger_type"]
    name = test["name"]
    mood = test.get("persona_mood", "?")
    situation = test.get("persona_situation", "?")
    resistance = test.get("persona_resistance", "?")

    print_section(f"TEST {i}/{total}: {name}")
    print(f"  Driver: {driver_id} | Trigger: {trigger_type}")
    print(f"  Mood: {mood} | Situation: {situation} | Resistance: {resistance}")

    payload = {
        "driver_id": driver_id,
        "trigger_type": trigger_type,
        "simulate": True,
    }
    # Add trigger-specific fields
    for key in ("severity", "fatigue_event_type", "erratic_sub_type", "g_force"):
        if key in test:
            payload[key] = test[key]
    # Add persona fields
    for key in ("persona_mood", "persona_situation", "persona_resistance"):
        if key in test:
            payload[key] = test[key]

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{BASE_URL}/api/triggers/trigger", json=payload)
        if resp.status_code != 200:
            return {"test": i, "name": name, "status": "FAIL", "error": resp.text,
                    "eval": {"score": 0, "max_score": 0, "pct": 0, "notes": ["API error"]}}

    transcript = await wait_for_call_end(driver_id)

    if not transcript:
        return {"test": i, "name": name, "status": "FAIL", "error": "No transcript",
                "eval": {"score": 0, "max_score": 0, "pct": 0, "notes": ["No transcript"]}}

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

    # Evaluate
    eval_result = evaluate_transcript(test, transcript)

    print(f"\n  Score: {eval_result['score']}/{eval_result['max_score']} ({eval_result['pct']}%)")
    for note in eval_result["notes"]:
        print(f"    - {note}")

    return {
        "test": i,
        "name": name,
        "driver_id": driver_id,
        "trigger_type": trigger_type,
        "mood": mood,
        "situation": situation,
        "resistance": resistance,
        "status": "PASS",
        "transcript_lines": len(transcript),
        "eval": eval_result,
    }


async def main():
    import httpx

    # Preflight
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: Set GEMINI_API_KEY")
        sys.exit(1)
    if not os.environ.get("BETTY_MEMORY_KEY"):
        print("ERROR: Set BETTY_MEMORY_KEY")
        sys.exit(1)

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{BASE_URL}/health")
            if resp.status_code != 200:
                raise Exception()
    except Exception:
        print(f"ERROR: Server not running at {BASE_URL}")
        print(f"Start it first: python -m uvicorn src.main:app --host 127.0.0.1 --port 8080")
        sys.exit(1)

    N = 20
    print_section(f"PERSONA TEST — {N} COMBINATIONS")

    tests = build_test_matrix(N)
    print(f"  Tests planned: {len(tests)}")
    for i, t in enumerate(tests, 1):
        print(f"    {i:2d}. {t['name']:20s} | {t['persona_mood']:12s} | "
              f"{t.get('persona_situation',''):20s} | {t.get('persona_resistance',''):12s} | "
              f"{t['trigger_type']}")

    # Clear memory for all drivers
    from src.memory.store import clear_memory
    for d in DRIVERS:
        clear_memory(d)
    print(f"\n  Memory cleared for all drivers")

    results = []
    for i, test in enumerate(tests, 1):
        if i > 1:
            print(f"\n  ... waiting 5s before next test ...")
            await asyncio.sleep(5)
        result = await run_test(i, len(tests), test)
        results.append(result)

    # --- Summary ---
    print_section("RESULTS SUMMARY")

    total_score = 0
    total_max = 0
    passed = 0
    failed = 0

    for r in results:
        ev = r["eval"]
        total_score += ev["score"]
        total_max += ev["max_score"]
        status_icon = "OK" if r["status"] == "PASS" else "XX"
        pct_str = f"{ev['pct']}%" if ev['max_score'] > 0 else "N/A"

        if r["status"] == "PASS":
            passed += 1
            print(f"  [{status_icon}] {r['test']:2d}. {r['name']:20s} | "
                  f"{r.get('mood',''):12s} | {r.get('situation',''):20s} | "
                  f"{r.get('resistance',''):12s} | "
                  f"Score: {ev['score']}/{ev['max_score']} ({pct_str})")
        else:
            failed += 1
            print(f"  [{status_icon}] {r['test']:2d}. {r['name']:20s} | "
                  f"FAILED: {r.get('error', 'unknown')}")

    overall_pct = round(total_score / total_max * 100) if total_max > 0 else 0

    print(f"\n  Calls: {passed} PASS / {failed} FAIL")
    print(f"  Overall persona score: {total_score}/{total_max} ({overall_pct}%)")

    # Breakdown by mood
    print_section("BREAKDOWN BY MOOD")
    mood_scores = {}
    for r in results:
        if r["status"] != "PASS":
            continue
        mood = r.get("mood", "?")
        if mood not in mood_scores:
            mood_scores[mood] = {"score": 0, "max": 0, "count": 0}
        mood_scores[mood]["score"] += r["eval"]["score"]
        mood_scores[mood]["max"] += r["eval"]["max_score"]
        mood_scores[mood]["count"] += 1

    for mood, s in sorted(mood_scores.items()):
        pct = round(s["score"] / s["max"] * 100) if s["max"] > 0 else 0
        print(f"  {mood:15s}: {s['score']}/{s['max']} ({pct}%) across {s['count']} tests")

    # Breakdown by resistance
    print_section("BREAKDOWN BY RESISTANCE")
    res_scores = {}
    for r in results:
        if r["status"] != "PASS":
            continue
        res = r.get("resistance", "?")
        if res not in res_scores:
            res_scores[res] = {"score": 0, "max": 0, "count": 0}
        res_scores[res]["score"] += r["eval"]["score"]
        res_scores[res]["max"] += r["eval"]["max_score"]
        res_scores[res]["count"] += 1

    for res, s in sorted(res_scores.items()):
        pct = round(s["score"] / s["max"] * 100) if s["max"] > 0 else 0
        print(f"  {res:15s}: {s['score']}/{s['max']} ({pct}%) across {s['count']} tests")

    print(f"\n{'='*80}")

    # Save results to JSON
    results_path = os.path.join(os.path.dirname(__file__), "..", "data", "persona_test_results.json")
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tests": len(tests),
            "passed": passed,
            "failed": failed,
            "overall_score": total_score,
            "overall_max": total_max,
            "overall_pct": overall_pct,
            "results": results,
        }, f, indent=2)
    print(f"\n  Full results saved to: {results_path}")


if __name__ == "__main__":
    asyncio.run(main())
