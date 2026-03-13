"""Automated conversation test: two Gemini Live sessions talk to each other.

- Session 1: Betty (AI companion, Aoede voice)
- Session 2: Simulated truck driver Mick (Puck voice)

Audio is stream-forwarded: each chunk is resampled and sent to the other
session as soon as it arrives (no collect-then-forward). This minimizes
latency between turns.

Usage:
    set GEMINI_API_KEY=your-key
    python tests/test_conversation.py
"""

import asyncio
import logging
import sys
import os
import time
import wave
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from google import genai
from google.genai import types

from src.voice.prompts import build_system_prompt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.INFO)
logging.getLogger("websockets").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash-native-audio-latest"
MAX_TURNS = 8
MAX_DURATION_S = 120
OUTPUT_RATE = 24000

DRIVER_SYSTEM_PROMPT = (
    "You are Mick, a 45-year-old Aussie truck driver on the Great Eastern Highway "
    "heading to Kalgoorlie. 3.5 hours in, a bit tired. You just got a phone call. "
    "Answer with a short greeting. Keep all responses to 1-2 sentences. "
    "Casual, laconic. Mention Coolgardie rest stop if asked about stopping. "
    "No formatted text."
)


def resample_24k_to_16k(pcm_24k: bytes) -> bytes:
    """Resample 16-bit PCM from 24kHz to 16kHz."""
    samples = np.frombuffer(pcm_24k, dtype=np.int16).astype(np.float64)
    if len(samples) == 0:
        return b""
    new_len = int(len(samples) * 16000 / 24000)
    indices = np.linspace(0, len(samples) - 1, new_len)
    return np.interp(indices, np.arange(len(samples)), samples).astype(np.int16).tobytes()


@dataclass
class AudioSegment:
    speaker: str
    pcm_data: bytes
    start_time: float


@dataclass
class TranscriptEntry:
    speaker: str
    text: str
    timestamp: float


def save_recording(segments: list[AudioSegment], t0: float):
    """Save conversation audio as a WAV file."""
    if not segments:
        return
    total_duration = max(
        s.start_time + len(s.pcm_data) / (OUTPUT_RATE * 2) for s in segments
    )
    total_samples = int(total_duration * OUTPUT_RATE) + OUTPUT_RATE  # +1s padding
    mixed = np.zeros(total_samples, dtype=np.float64)

    for seg in segments:
        samples = np.frombuffer(seg.pcm_data, dtype=np.int16).astype(np.float64)
        start = int(seg.start_time * OUTPUT_RATE)
        end = min(start + len(samples), total_samples)
        if start >= 0:
            mixed[start:end] += samples[: end - start]

    mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(t0))
    filename = os.path.join(os.path.dirname(__file__), f"conversation_{ts}.wav")

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(OUTPUT_RATE)
        wf.writeframes(mixed.tobytes())

    logger.info("Recording saved: %s (%.1fs)", filename, total_duration)


async def stream_turn(source_session, target_session, speaker: str,
                      transcript: list, audio_segments: list, t0: float):
    """Receive one turn from source, stream-forward audio to target in real-time.

    Audio chunks are resampled and forwarded as they arrive — no waiting
    for the full turn. Activity signals bracket the forwarded audio.
    """
    chunks_24k = []
    sent_activity_start = False
    first_audio_time = None

    async for resp in source_session.receive():
        sc = resp.server_content
        if not sc:
            continue

        if sc.model_turn and sc.model_turn.parts:
            for part in sc.model_turn.parts:
                if part.inline_data and part.inline_data.data:
                    audio_data = part.inline_data.data
                    chunks_24k.append(audio_data)

                    if not first_audio_time:
                        first_audio_time = time.time() - t0

                    # Stream-forward: resample and send immediately
                    if not sent_activity_start:
                        await target_session.send_realtime_input(
                            activity_start=types.ActivityStart()
                        )
                        sent_activity_start = True

                    pcm_16k = resample_24k_to_16k(audio_data)
                    if pcm_16k:
                        await target_session.send_realtime_input(
                            audio={"data": pcm_16k, "mime_type": "audio/pcm"}
                        )

        # Capture transcript
        ot = getattr(sc, "output_transcription", None)
        if ot and ot.text:
            text = ot.text.strip()
            if text:
                transcript.append(TranscriptEntry(speaker, text, time.time() - t0))

        if sc.turn_complete:
            break

    # Signal end of speech
    if sent_activity_start:
        await target_session.send_realtime_input(
            activity_end=types.ActivityEnd()
        )

    # Save audio segment for recording
    if chunks_24k:
        audio_segments.append(AudioSegment(
            speaker=speaker,
            pcm_data=b"".join(chunks_24k),
            start_time=first_audio_time or (time.time() - t0),
        ))

    return len(chunks_24k) > 0


async def run_conversation():
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: Set GEMINI_API_KEY environment variable")
        sys.exit(1)

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    transcript: list[TranscriptEntry] = []
    audio_segments: list[AudioSegment] = []
    t0 = time.time()

    betty_prompt = build_system_prompt(
        driver_name="Mick",
        trigger_type="companion_check_in",
        route="Perth to Kalgoorlie via Great Eastern Highway",
        hours_driven=3.5,
    )

    def make_config(system_prompt: str, voice: str) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=system_prompt)]
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=True
                ),
            ),
        )

    betty_config = make_config(betty_prompt, "Aoede")
    driver_config = make_config(DRIVER_SYSTEM_PROMPT, "Puck")

    async with (
        client.aio.live.connect(model=MODEL, config=betty_config) as betty,
        client.aio.live.connect(model=MODEL, config=driver_config) as driver,
    ):
        print(f"\n{'='*50}")
        print(f"  Automated Conversation: Betty <-> Mick")
        print(f"  Max turns: {MAX_TURNS} | Timeout: {MAX_DURATION_S}s")
        print(f"{'='*50}\n")

        # Driver answers the phone first
        logger.info("Mick answering the phone...")
        await driver.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text="Your phone is ringing. Pick it up.")],
            ),
            turn_complete=True,
        )

        turn = 0
        while turn < MAX_TURNS and (time.time() - t0) < MAX_DURATION_S:
            turn += 1
            if turn % 2 == 1:
                speaker, source, target = "Mick", driver, betty
            else:
                speaker, source, target = "Betty", betty, driver

            turn_start = time.time()
            logger.info("Turn %d: %s speaking...", turn, speaker)

            has_audio = await asyncio.wait_for(
                stream_turn(source, target, speaker, transcript, audio_segments, t0),
                timeout=30,
            )

            if not has_audio:
                logger.warning("Turn %d: %s produced no audio", turn, speaker)
                break

            elapsed = time.time() - turn_start
            # Show latest transcript for this turn
            turn_texts = [e for e in transcript if e.speaker == speaker]
            if turn_texts:
                full = " ".join(e.text for e in turn_texts[-8:])
                print(f"  [{speaker}]: {full}")

            logger.info("Turn %d: %s done (%.1fs including stream-forward)", turn, speaker, elapsed)

        logger.info("Conversation ended after %d turns in %.1fs", turn, time.time() - t0)

    # Save recording
    if audio_segments:
        save_recording(audio_segments, t0)

    # Print final transcript
    print(f"\n{'='*50}")
    print(f"  FULL TRANSCRIPT")
    print(f"{'='*50}")
    for entry in transcript:
        print(f"  [{entry.timestamp:5.1f}s] {entry.speaker}: {entry.text}")
    print(f"{'='*50}")
    print(f"  Turns: {turn} | Duration: {time.time() - t0:.1f}s")
    print(f"{'='*50}")


if __name__ == "__main__":
    try:
        asyncio.run(run_conversation())
    except KeyboardInterrupt:
        print("\nInterrupted.")
