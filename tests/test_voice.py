"""Standalone test: open Gemini Live session, converse with Betty via mic/speaker.

Uses noise-floor gating: samples ambient noise, then only sends audio to
Gemini when it's above the noise floor. Below threshold, sends silence.
This lets Gemini's built-in VAD work naturally without false triggers from
background noise (engine, road, wind).

Usage:
    set GEMINI_API_KEY=your-key
    python tests/test_voice.py
"""

import asyncio
import logging
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyaudio
import numpy as np

from src.voice.prompts import build_system_prompt
from src.voice.gemini_live import GeminiLiveSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.INFO)
logging.getLogger("websockets").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_RATE = 16000
RECV_RATE = 24000
CHUNK = 1024

# Noise gate settings
NOISE_SAMPLE_SECONDS = 2
RMS_MULTIPLIER = 2.5  # Speech must be this far above noise floor

pya = pyaudio.PyAudio()
audio_out_queue = asyncio.Queue()
SILENCE_CHUNK = b'\x00' * (CHUNK * 2)  # 16-bit silence

stats = {"turns": 0, "audio_bytes_out": 0, "gated_chunks": 0, "passed_chunks": 0}
start_time = None


def rms(pcm_data: bytes) -> float:
    """Calculate RMS of 16-bit PCM audio."""
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float64)
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples ** 2)))


def sample_noise_floor(mic_stream, duration_s: float) -> float:
    """Record ambient noise and return peak RMS as baseline."""
    logger.info("Sampling ambient noise for %.1fs — stay quiet...", duration_s)
    chunks_needed = int(SEND_RATE / CHUNK * duration_s)
    rms_values = []
    for _ in range(chunks_needed):
        data = mic_stream.read(CHUNK, exception_on_overflow=False)
        rms_values.append(rms(data))
    noise_rms = float(np.mean(rms_values))
    noise_peak = float(np.max(rms_values))
    logger.info("Noise floor: mean=%.1f, peak=%.1f", noise_rms, noise_peak)
    return noise_peak


async def listen_mic(session: GeminiLiveSession, threshold: float):
    """Capture mic audio, gate by noise floor, send to Gemini."""
    mic_info = pya.get_default_input_device_info()
    logger.info("Mic: %s", mic_info["name"])
    stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT, channels=CHANNELS, rate=SEND_RATE,
        input=True, input_device_index=mic_info["index"],
        frames_per_buffer=CHUNK,
    )
    try:
        while True:
            data = await asyncio.to_thread(stream.read, CHUNK, **{"exception_on_overflow": False})
            level = rms(data)

            if level > threshold:
                # Real speech — send actual audio
                await session.send_audio(data)
                stats["passed_chunks"] += 1
            else:
                # Below noise floor — send silence so VAD sees quiet
                await session.send_audio(SILENCE_CHUNK)
                stats["gated_chunks"] += 1
    finally:
        stream.close()


async def play_audio():
    """Play audio chunks from the output queue."""
    stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT, channels=CHANNELS, rate=RECV_RATE, output=True,
    )
    try:
        while True:
            data = await audio_out_queue.get()
            await asyncio.to_thread(stream.write, data)
    finally:
        stream.close()


def on_audio(data: bytes):
    stats["audio_bytes_out"] += len(data)
    if stats["audio_bytes_out"] == len(data):
        elapsed = time.time() - start_time if start_time else 0
        logger.info("First audio from Betty after %.1fs", elapsed)
    audio_out_queue.put_nowait(data)


def on_text(text: str):
    stripped = text.strip()
    if stripped.startswith("**"):
        return  # filter thinking text
    print(f"\n[Betty]: {text}")


def on_turn_complete():
    stats["turns"] += 1
    duration = stats["audio_bytes_out"] / (RECV_RATE * 2) if stats["audio_bytes_out"] else 0
    logger.info("Turn %d complete | Betty spoke %.1fs | mic: %d passed, %d gated",
                stats["turns"], duration, stats["passed_chunks"], stats["gated_chunks"])
    stats["audio_bytes_out"] = 0
    stats["passed_chunks"] = 0
    stats["gated_chunks"] = 0


def on_interrupted():
    cleared = 0
    while not audio_out_queue.empty():
        try:
            audio_out_queue.get_nowait()
            cleared += 1
        except asyncio.QueueEmpty:
            break
    if cleared:
        logger.info("Interrupted: cleared %d audio chunks", cleared)


async def main():
    global start_time

    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: Set GEMINI_API_KEY environment variable")
        sys.exit(1)

    # Sample noise floor
    mic_info = pya.get_default_input_device_info()
    mic_stream = pya.open(
        format=FORMAT, channels=CHANNELS, rate=SEND_RATE,
        input=True, input_device_index=mic_info["index"],
        frames_per_buffer=CHUNK,
    )
    noise_floor = sample_noise_floor(mic_stream, NOISE_SAMPLE_SECONDS)
    mic_stream.close()
    threshold = noise_floor * RMS_MULTIPLIER

    system_prompt = build_system_prompt(
        driver_name="Mick",
        trigger_type="companion_check_in",
        route="Perth to Kalgoorlie via Great Eastern Highway",
        hours_driven=3.5,
    )

    session = GeminiLiveSession(
        system_prompt=system_prompt,
        voice="Aoede",
        on_audio=on_audio,
        on_text=on_text,
        on_turn_complete=on_turn_complete,
        on_interrupted=on_interrupted,
    )

    try:
        await session.connect()
        session.start_receiving()
        start_time = time.time()

        print("\n=== Betty voice test ===")
        print(f"  Noise gate threshold: {threshold:.0f} RMS")
        print(f"  (noise floor {noise_floor:.0f} x {RMS_MULTIPLIER})")
        print()
        print("  Say 'Hello?' — you're the driver answering the call.")
        print("  Betty will respond and you can have a conversation.")
        print("  Ctrl+C to quit")
        print("========================\n")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(listen_mic(session, threshold))
            tg.create_task(play_audio())

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n--- Ending conversation ---")
    except ExceptionGroup as eg:
        for e in eg.exceptions:
            if not isinstance(e, (KeyboardInterrupt, asyncio.CancelledError)):
                logger.error("Task error: %s: %s", type(e).__name__, e)
    finally:
        await session.close()
        pya.terminate()
        logger.info("Done. Total turns: %d", stats["turns"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted.")
