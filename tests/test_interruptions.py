"""Test: run 10 simulated interruption calls, capture transcripts + logs.

Analyses interrupt behaviour: did the driver actually cut Betty off?
Does Betty acknowledge being interrupted? Does the conversation sound natural?
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load env vars from Windows user environment
for var in ("GEMINI_API_KEY", "BETTY_MEMORY_KEY"):
    if var not in os.environ:
        result = subprocess.run(
            ["powershell", "-Command",
             f'[System.Environment]::GetEnvironmentVariable("{var}", "User")'],
            capture_output=True, text=True,
        )
        val = result.stdout.strip()
        if val:
            os.environ[var] = val

# Capture logs from simulated_call
log_records: list[logging.LogRecord] = []


class LogCapture(logging.Handler):
    def emit(self, record):
        log_records.append(record)


capture_handler = LogCapture()
capture_handler.setLevel(logging.DEBUG)

# Set up logging
logging.basicConfig(level="INFO", format="%(name)s %(levelname)s %(message)s")
logging.getLogger("src.call.simulated_call").addHandler(capture_handler)
logging.getLogger("src.call.simulated_call").setLevel(logging.DEBUG)

from src.call.simulated_call import run_simulated_call
from src.call.call_manager import CallManager

NUM_RUNS = 10
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "interruption_results.json")


def analyse_run(run_idx: int, result: dict, run_logs: list[str]) -> dict:
    """Analyse a single run for interrupt quality."""
    transcript = result.get("transcript", [])
    turns = result.get("turns", 0)
    duration = result.get("duration", 0)

    # Count interrupt-related log lines
    interrupt_triggered = sum(1 for l in run_logs if "interrupting Betty" in l)
    interrupt_turns = sum(1 for l in run_logs if "driver will interrupt Betty" in l)
    interrupt_cut_in = sum(1 for l in run_logs if "will cut in after" in l)

    # Analyse transcript for natural interrupt markers
    betty_lines = [t for t in transcript if t["speaker"] == "Betty"]
    driver_lines = [t for t in transcript if t["speaker"] != "Betty"]

    # Check for signs Betty acknowledged being cut off
    acknowledge_phrases = [
        "sorry", "go ahead", "what were you", "you were saying",
        "didn't catch", "say that again", "interrupted", "cut",
        "hear you", "listen", "go on", "yeah?", "right",
    ]
    betty_acknowledged = 0
    for line in betty_lines:
        text_lower = line["text"].lower()
        if any(p in text_lower for p in acknowledge_phrases):
            betty_acknowledged += 1

    # Check for abrupt driver lines (short, cutting in)
    short_driver_lines = sum(1 for l in driver_lines if len(l["text"].split()) <= 8)

    # Check for incomplete Betty sentences (sign of being cut off)
    incomplete_betty = 0
    for line in betty_lines:
        text = line["text"].strip()
        if text and not text[-1] in ".!?\"'":
            incomplete_betty += 1

    return {
        "run": run_idx + 1,
        "status": result.get("status"),
        "turns": turns,
        "duration": round(duration, 1),
        "transcript_lines": len(transcript),
        "betty_lines": len(betty_lines),
        "driver_lines": len(driver_lines),
        "interrupt_turns_planned": interrupt_turns,
        "interrupt_cut_in_logged": interrupt_cut_in,
        "interrupts_triggered": interrupt_triggered,
        "betty_acknowledged_interrupt": betty_acknowledged,
        "incomplete_betty_sentences": incomplete_betty,
        "short_driver_interjections": short_driver_lines,
        "transcript": transcript,
        "logs": run_logs,
    }


async def run_single(run_idx: int) -> dict:
    """Run one interruption call and return analysis."""
    log_records.clear()
    cm = CallManager()

    print(f"\n{'='*60}")
    print(f"  RUN {run_idx + 1}/{NUM_RUNS}")
    print(f"{'='*60}")

    t0 = time.time()
    result = await run_simulated_call(
        driver_id="DRV-001",
        trigger_type="fatigue_camera",
        trigger_data={"fatigue_event_type": "droopy_eyes", "severity": "high"},
        call_manager=cm,
        persona={
            "mood": "grumpy",
            "situation": "argument_dispatch",
            "resistance": "resistant",
            "interrupts": True,
        },
    )
    elapsed = time.time() - t0

    # Capture logs for this run
    run_logs = [r.getMessage() for r in log_records]

    # Print transcript
    print(f"\nTranscript ({result.get('turns')} turns, {elapsed:.1f}s):")
    for t in result.get("transcript", []):
        speaker = t["speaker"]
        marker = "  " if speaker == "Betty" else ">>"
        print(f"  {marker} [{speaker}] {t['text']}")

    # Print interrupt logs
    interrupt_logs = [l for l in run_logs if "interrupt" in l.lower()]
    if interrupt_logs:
        print(f"\nInterrupt logs:")
        for l in interrupt_logs:
            print(f"  {l}")

    analysis = analyse_run(run_idx, result, run_logs)
    print(f"\nAnalysis: {analysis['interrupts_triggered']} interrupts triggered, "
          f"{analysis['betty_acknowledged_interrupt']} acknowledged, "
          f"{analysis['incomplete_betty_sentences']} incomplete Betty sentences")

    return analysis


async def main():
    all_results = []

    for i in range(NUM_RUNS):
        try:
            analysis = await run_single(i)
            all_results.append(analysis)
        except Exception as e:
            print(f"\nRUN {i+1} FAILED: {e}")
            all_results.append({"run": i + 1, "status": "error", "error": str(e)})

        # Brief pause between runs
        if i < NUM_RUNS - 1:
            await asyncio.sleep(2)

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY ({NUM_RUNS} runs)")
    print(f"{'='*60}")

    successful = [r for r in all_results if r.get("status") == "completed"]
    failed = [r for r in all_results if r.get("status") != "completed"]

    if successful:
        avg_turns = sum(r["turns"] for r in successful) / len(successful)
        avg_duration = sum(r["duration"] for r in successful) / len(successful)
        total_interrupts = sum(r["interrupts_triggered"] for r in successful)
        total_acknowledged = sum(r["betty_acknowledged_interrupt"] for r in successful)
        total_incomplete = sum(r["incomplete_betty_sentences"] for r in successful)
        runs_with_interrupts = sum(1 for r in successful if r["interrupts_triggered"] > 0)

        print(f"  Successful runs: {len(successful)}/{NUM_RUNS}")
        print(f"  Failed runs: {len(failed)}")
        print(f"  Avg turns: {avg_turns:.1f}")
        print(f"  Avg duration: {avg_duration:.1f}s")
        print(f"  Runs with interrupts: {runs_with_interrupts}/{len(successful)}")
        print(f"  Total interrupts triggered: {total_interrupts}")
        print(f"  Total Betty acknowledged: {total_acknowledged}")
        print(f"  Total incomplete Betty sentences: {total_incomplete}")

    # Save full results
    # Strip logs for JSON (keep transcripts)
    save_results = []
    for r in all_results:
        save = {k: v for k, v in r.items() if k != "logs"}
        save_results.append(save)

    with open(RESULTS_PATH, "w") as f:
        json.dump(save_results, f, indent=2)
    print(f"\n  Results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
