"""Test: simulated break_limit call to see if Betty sends a rest stop card."""

import asyncio
import logging
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for var in ("GEMINI_API_KEY", "BETTY_MEMORY_KEY"):
    if var not in os.environ:
        result = subprocess.run(
            ["powershell", "-Command",
             f'[System.Environment]::GetEnvironmentVariable("{var}", "User")'],
            capture_output=True, text=True
        )
        val = result.stdout.strip()
        if val:
            os.environ[var] = val

logging.basicConfig(level="INFO", format="%(name)s %(levelname)s %(message)s")

from src.call.simulated_call import run_simulated_call
from src.call.call_manager import CallManager


async def main():
    cm = CallManager()
    result = await run_simulated_call(
        driver_id="DRV-001",
        trigger_type="break_limit",
        trigger_data={},
        call_manager=cm,
        persona={"mood": "exhausted", "situation": "normal", "resistance": "cooperative"},
    )
    print(f"\nResult: {result.get('status')}, {result.get('turns')} turns, {result.get('duration')}s")
    for t in result.get("transcript", []):
        print(f"  [{t['speaker']}] {t['text']}")


if __name__ == "__main__":
    asyncio.run(main())
