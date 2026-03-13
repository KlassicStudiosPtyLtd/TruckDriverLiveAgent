"""Test tool calling in a Gemini Live voice conversation.

Usage:
    export GEMINI_API_KEY=your-key
    python tests/test_tools.py

Asks Betty about Mick's hours — she should call get_driver_hours and speak the answer.
"""

import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyaudio

from src.voice.prompts import build_system_prompt, get_speaks_first_message
from src.voice.gemini_live import GeminiLiveSession
from src.tools.betty_tools import TOOL_DECLARATIONS, handle_tool_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_RATE = 24000
INPUT_RATE = 16000
INPUT_CHUNK = 1600


async def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: Set GEMINI_API_KEY environment variable")
        sys.exit(1)

    system_prompt = build_system_prompt(
        driver_name="Mick",
        trigger_type="fatigue_camera",
        route="Perth to Kalgoorlie via Great Eastern Highway",
        hours_driven=3.5,
        fatigue_event_type="droopy_eyes",
        severity="medium",
    )

    pa = pyaudio.PyAudio()

    out_stream = pa.open(
        format=pyaudio.paInt16, channels=1, rate=OUTPUT_RATE,
        output=True, frames_per_buffer=4800,
    )
    in_stream = pa.open(
        format=pyaudio.paInt16, channels=1, rate=INPUT_RATE,
        input=True, frames_per_buffer=INPUT_CHUNK,
    )

    def on_audio(data: bytes):
        out_stream.write(data)

    def on_text(text: str):
        print(f"\n[Betty]: {text}")

    def on_turn_complete():
        print("[Turn complete]")

    session = GeminiLiveSession(
        system_prompt=system_prompt,
        voice="Aoede",
        tools=TOOL_DECLARATIONS,
        tool_handler=handle_tool_call,
        on_audio=on_audio,
        on_text=on_text,
        on_turn_complete=on_turn_complete,
    )

    try:
        await session.connect()
        session.start_receiving()

        speaks_first = get_speaks_first_message("fatigue_camera")
        await session.send_text(speaks_first)

        print("\n--- Betty with tools. Ask about Mick's hours! Ctrl+C to quit. ---\n")

        while True:
            pcm = in_stream.read(INPUT_CHUNK, exception_on_overflow=False)
            await session.send_audio(pcm)
            await asyncio.sleep(0)

    except KeyboardInterrupt:
        print("\n--- Done ---")
    finally:
        await session.close()
        in_stream.stop_stream()
        in_stream.close()
        out_stream.stop_stream()
        out_stream.close()
        pa.terminate()


if __name__ == "__main__":
    asyncio.run(main())
