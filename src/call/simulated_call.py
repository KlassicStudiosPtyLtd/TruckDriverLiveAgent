"""Simulated call: two Gemini Live sessions talk to each other.

Betty (Aoede) <-> Driver persona (Puck). Audio is stream-forwarded
between sessions with 24k->16k resampling. Transcript and audio
are broadcast to the dashboard in real-time.
"""

import asyncio
import json
import logging
import os
import random
import time
import wave
from dataclasses import dataclass
from typing import Optional

import numpy as np
from google import genai
from google.genai import types

from src.call.call_manager import CallManager
from src.data.mock_fleet import get_driver, get_driver_hours, get_recent_events
from src.memory.store import add_entry as add_memory_entry, get_memory_summary
from src.tools.betty_tools import (
    TOOL_DECLARATIONS, handle_tool_call,
    set_card_callback, set_trigger_context,
)
from src.call.video_frames import extract_frames
from src.voice.prompts import build_system_prompt

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash-native-audio-latest"
MAX_TURNS = 8
MAX_DURATION_S = 120
OUTPUT_RATE = 24000
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "recordings")
PERSONAS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "mock", "driver_personas.json")
CABIN_NOISE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "static", "sfx", "cabin_noise.pcm")
CABIN_NOISE_GAIN = 0.8  # clearly audible in-cab ambience

# Pre-load cabin noise into memory as float64 for fast mixing
_cabin_noise: Optional[np.ndarray] = None


def _get_cabin_noise() -> np.ndarray:
    """Load cabin noise PCM (lazy, cached)."""
    global _cabin_noise
    if _cabin_noise is None:
        raw = open(CABIN_NOISE_PATH, "rb").read()
        _cabin_noise = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
        logger.info("Loaded cabin noise: %.1fs", len(_cabin_noise) / OUTPUT_RATE)
    return _cabin_noise


def _mix_cabin_noise(pcm_data: bytes, noise_cursor: int) -> tuple[bytes, int]:
    """Mix cabin noise into a PCM chunk. Returns mixed bytes and new cursor."""
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float64)
    if len(samples) == 0:
        return pcm_data, noise_cursor
    noise = _get_cabin_noise()
    n_len = len(noise)

    # Extract looping noise segment
    end = noise_cursor + len(samples)
    if end <= n_len:
        noise_slice = noise[noise_cursor:end]
    else:
        # Wrap around
        noise_slice = np.concatenate([noise[noise_cursor:], noise[:end % n_len]])
    new_cursor = end % n_len

    mixed = samples + noise_slice * CABIN_NOISE_GAIN
    return np.clip(mixed, -32768, 32767).astype(np.int16).tobytes(), new_cursor


_personas_data: Optional[dict] = None


def _load_personas() -> dict:
    """Load driver persona presets (lazy, cached)."""
    global _personas_data
    if _personas_data is None:
        with open(PERSONAS_PATH, "r") as f:
            _personas_data = json.load(f)
        logger.info("Loaded %d moods, %d situations, %d presets",
                     len(_personas_data["moods"]),
                     len(_personas_data["situations"]),
                     len(_personas_data.get("preset_combinations", [])))
    return _personas_data


def get_random_persona() -> dict:
    """Pick a random preset combination."""
    data = _load_personas()
    presets = data.get("preset_combinations", [])
    return random.choice(presets) if presets else {}


def build_persona_prompt(mood: str = "", situation: str = "",
                         resistance: str = "") -> str:
    """Build persona prompt fragments from keys."""
    data = _load_personas()
    parts = []
    if mood and mood in data["moods"]:
        parts.append(data["moods"][mood]["prompt"])
    if situation and situation in data["situations"]:
        s = data["situations"][situation]["prompt"]
        if s:
            parts.append(s)
    if resistance and resistance in data["resistance_levels"]:
        parts.append(data["resistance_levels"][resistance]["prompt"])
    return " ".join(parts)


@dataclass
class AudioSegment:
    speaker: str
    pcm_data: bytes
    start_time: float


def _save_recording(segments: list[AudioSegment], driver_id: str,
                    trigger_type: str, t0: float) -> Optional[str]:
    """Save conversation audio as a WAV file."""
    if not segments:
        return None

    os.makedirs(RECORDINGS_DIR, exist_ok=True)

    total_duration = max(
        s.start_time + len(s.pcm_data) / (OUTPUT_RATE * 2) for s in segments
    )
    total_samples = int(total_duration * OUTPUT_RATE) + OUTPUT_RATE
    mixed = np.zeros(total_samples, dtype=np.float64)

    for seg in segments:
        samples = np.frombuffer(seg.pcm_data, dtype=np.int16).astype(np.float64)
        start = int(seg.start_time * OUTPUT_RATE)
        end = min(start + len(samples), total_samples)
        if start >= 0:
            mixed[start:end] += samples[:end - start]

    mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(t0))
    filename = os.path.join(RECORDINGS_DIR, f"{driver_id}_{trigger_type}_{ts}.wav")

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(OUTPUT_RATE)
        wf.writeframes(mixed.tobytes())

    logger.info("Recording saved: %s (%.1fs)", filename, total_duration)
    return filename


def _resample_24k_to_16k(pcm_24k: bytes) -> bytes:
    samples = np.frombuffer(pcm_24k, dtype=np.int16).astype(np.float64)
    if len(samples) == 0:
        return b""
    new_len = int(len(samples) * 16000 / 24000)
    indices = np.linspace(0, len(samples) - 1, new_len)
    return np.interp(indices, np.arange(len(samples)), samples).astype(np.int16).tobytes()


def _build_driver_persona(driver: dict, trigger_type: str, trigger_data: dict,
                          persona: dict | None = None) -> str:
    """Build a short system prompt for the simulated driver.

    persona is an optional dict with keys: mood, situation, resistance.
    If not provided, a random preset is chosen.
    """
    name = driver["first_name"]
    route = driver.get("current_route", "a long haul route")

    # --- Trigger-specific context (what just happened) ---
    trigger_context = ""
    if trigger_type == "fatigue_camera":
        severity = trigger_data.get("severity", "medium")
        event = trigger_data.get("fatigue_event_type", "")

        if severity == "high":
            trigger_context = "You're very tired but don't want to admit it."
        elif severity == "medium":
            trigger_context = "You're a bit tired but reckon you can push through."
        else:
            trigger_context = "You're feeling mostly okay."

        if event == "droopy_eyes":
            trigger_context += " Your eyes feel heavy and you keep rubbing them."
        elif event == "yawning":
            trigger_context += " You've been yawning a fair bit."
        elif event == "head_nod":
            trigger_context += " You caught yourself nodding off for a second but you won't say that."
        elif event == "distraction":
            trigger_context += " You were fiddling with the radio, nothing serious."
        elif event == "phone_use":
            trigger_context += " You were checking your phone for messages. You know you shouldn't."
        elif event == "smoking":
            trigger_context += " You lit up a durry to try and stay awake."

    elif trigger_type == "erratic_driving":
        sub = trigger_data.get("erratic_sub_type", "")
        g = trigger_data.get("g_force")

        if sub == "lane_deviation":
            trigger_context = "You drifted a bit on the road. Maybe the wind caught the trailer, or you were distracted for a sec."
        elif sub == "harsh_braking":
            trigger_context = "You had to slam on the brakes. Reckon there was a roo on the road, or you were following too close."
        elif sub == "excessive_sway":
            trigger_context = "The truck's been swaying a bit. Could be the road surface or maybe the load shifted."
        elif sub == "rollover_intervention":
            trigger_context = "The stability system kicked in on a bend. Gave you a fright but you reckon you're fine."
        else:
            trigger_context = "You swerved a bit or braked hard. You think it was nothing."

        if g and g > 0.5:
            trigger_context += " It was a pretty solid jolt."

    elif trigger_type == "break_limit":
        trigger_context = (
            "You've been driving a while and you know you should stop soon "
            "but you want to make good time. You'll mention you're close to your destination if pushed."
        )

    # --- Persona layer (mood + situation + resistance) ---
    if persona is None:
        persona = get_random_persona()

    persona_prompt = build_persona_prompt(
        mood=persona.get("mood", ""),
        situation=persona.get("situation", ""),
        resistance=persona.get("resistance", ""),
    )

    persona_name = persona.get("name", "")
    if persona_name:
        logger.info("Driver persona: %s (mood=%s, situation=%s, resistance=%s)",
                     persona_name, persona.get("mood"), persona.get("situation"),
                     persona.get("resistance"))

    # Combine: trigger context first (what happened), then persona (how they feel about it)
    combined = " ".join(filter(None, [trigger_context, persona_prompt]))

    # Driver-initiated: driver is calling Betty
    if trigger_type == "driver_initiated":
        return (
            f"You are {name}, an Aussie truck driver on {route}. "
            f"You're calling Betty, your AI companion, for a yarn. "
            f"Start with a greeting like 'Hey Betty!' or 'G'day Bet, how's it going?'. "
            f"Keep all responses to 1-2 sentences. Casual, laconic Australian style. "
            f"{combined} "
            f"No formatted text."
        )

    return (
        f"You are {name}, an Aussie truck driver on {route}. "
        f"You just got a phone call. Answer with a short greeting like 'Yeah, hello?' or 'G'day'. "
        f"Keep all responses to 1-2 sentences. Casual, laconic Australian style. "
        f"{combined} "
        f"No formatted text."
    )


def _make_config(system_prompt: str, voice: str, tools: Optional[list] = None) -> types.LiveConnectConfig:
    config = types.LiveConnectConfig(
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
    if tools:
        config.tools = [types.Tool(function_declarations=tools)]
    return config


async def _stream_turn(source_session, target_session, speaker: str,
                       on_transcript, on_audio, t0: float,
                       cancel_event: asyncio.Event,
                       audio_segments: list[AudioSegment] | None = None,
                       is_driver: bool = False,
                       noise_cursor: int = 0) -> tuple[bool, int]:
    """Receive one turn from source, stream-forward audio to target.

    Returns (had_audio, noise_cursor).
    """
    chunks = []
    segment_start = time.time() - t0
    sent_activity_start = False
    cur = noise_cursor

    async for resp in source_session.receive():
        if cancel_event.is_set():
            break

        sc = resp.server_content

        if resp.tool_call and speaker == "Betty":
            results = []
            for fc in resp.tool_call.function_calls:
                logger.info("Sim tool call: %s(%s)", fc.name, fc.args)
                result = await handle_tool_call(fc.name, fc.args or {})
                results.append(types.FunctionResponse(
                    name=fc.name, id=fc.id, response=result,
                ))
            await source_session.send_tool_response(function_responses=results)
            continue

        if not sc:
            continue

        if sc.model_turn and sc.model_turn.parts:
            for part in sc.model_turn.parts:
                if part.inline_data and part.inline_data.data:
                    audio_data = part.inline_data.data

                    # Mix cabin noise for driver speech (Betty hears road noise)
                    if is_driver:
                        audio_data, cur = _mix_cabin_noise(audio_data, cur)

                    chunks.append(audio_data)

                    if not sent_activity_start:
                        await target_session.send_realtime_input(
                            activity_start=types.ActivityStart()
                        )
                        sent_activity_start = True

                    pcm_16k = _resample_24k_to_16k(audio_data)
                    if pcm_16k:
                        await target_session.send_realtime_input(
                            audio={"data": pcm_16k, "mime_type": "audio/pcm"}
                        )

                    # Stream audio to dashboard (cabin noise is played
                    # as a continuous loop client-side)
                    if on_audio:
                        await on_audio(audio_data)

        ot = getattr(sc, "output_transcription", None)
        if ot and ot.text:
            text = ot.text.strip()
            if text:
                logger.info("Sim transcript [%s]: %s", speaker, text)
                if on_transcript:
                    await on_transcript(speaker, text, time.time() - t0)

        if sc.turn_complete:
            break

    if sent_activity_start:
        await target_session.send_realtime_input(
            activity_end=types.ActivityEnd()
        )

    # Save combined audio for recording
    if audio_segments is not None and chunks:
        combined = b"".join(chunks)
        audio_segments.append(AudioSegment(
            speaker=speaker,
            pcm_data=combined,
            start_time=segment_start,
        ))

    return len(chunks) > 0, cur


async def run_simulated_call(
    driver_id: str,
    trigger_type: str,
    trigger_data: dict,
    call_manager: CallManager,
    persona: dict | None = None,
) -> dict:
    """Run a fully simulated call between Betty and a driver persona."""
    driver = get_driver(driver_id)
    if not driver:
        return {"error": f"Unknown driver: {driver_id}"}

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}

    hours = get_driver_hours(driver_id)
    events = get_recent_events(driver_id)
    event_summary = f"{len(events)} recent events" if events else None
    memory_summary = get_memory_summary(driver_id)

    betty_prompt = build_system_prompt(
        driver_name=driver["first_name"],
        trigger_type=trigger_type,
        route=driver.get("current_route"),
        hours_driven=hours["hours_driven_continuous"] if hours else None,
        recent_event_summary=event_summary,
        memory_summary=memory_summary,
        fatigue_event_type=trigger_data.get("fatigue_event_type"),
        severity=trigger_data.get("severity"),
        erratic_sub_type=trigger_data.get("erratic_sub_type"),
        g_force=trigger_data.get("g_force"),
        hours_driven_continuous=hours["hours_driven_continuous"] if hours else None,
        minutes_until_mandatory_break=hours["minutes_until_mandatory_break"] if hours else None,
        next_rest_area_name=hours.get("next_rest_area_name") if hours else None,
        next_rest_area_km=hours.get("next_rest_area_km") if hours else None,
    )

    driver_persona = _build_driver_persona(driver, trigger_type, trigger_data, persona)

    # Track call + cancellation
    call = call_manager.initiate_call(driver_id, trigger_type, trigger_data)
    call.status = "connected"
    call_manager._active_calls[driver_id] = call_manager._pending_calls.pop(driver_id)

    cancel_event = asyncio.Event()
    call.cancel_event = cancel_event  # so end_call can signal it

    await call_manager.broadcast_to_dashboard({
        "type": "call_started",
        "driver_id": driver_id,
        "call_id": call.call_id,
        "trigger_type": trigger_type,
        "simulated": True,
    })

    transcript_entries = []
    audio_segments: list[AudioSegment] = []
    call.transcript = transcript_entries
    t0 = time.time()

    async def on_transcript(speaker: str, text: str, timestamp: float):
        entry = {"speaker": speaker, "text": text, "time": round(timestamp, 1)}
        transcript_entries.append(entry)
        await call_manager.broadcast_to_dashboard({
            "type": "transcript",
            "driver_id": driver_id,
            "speaker": speaker.lower(),
            "text": text,
        })

    async def on_audio(audio_data: bytes):
        """Stream 24kHz PCM audio to all connected dashboard WebSockets."""
        await call_manager.broadcast_audio_to_dashboard(audio_data)

    # Set up card callback so tool handlers can broadcast cards to dashboard
    async def _on_card(**kwargs):
        await call_manager.broadcast_to_dashboard({
            "type": "card",
            "card_type": kwargs.get("card_type", ""),
            "driver_id": kwargs.get("driver_id", driver_id),
            "image_url": kwargs.get("image_url", ""),
        })
    set_card_callback(_on_card)
    set_trigger_context(trigger_type, trigger_data)

    client = genai.Client(api_key=api_key)
    betty_config = _make_config(betty_prompt, "Aoede", tools=TOOL_DECLARATIONS)
    driver_config = _make_config(driver_persona, "Puck")

    turn_count = 0
    noise_cursor = 0  # continuous cabin noise position
    try:
        async with (
            client.aio.live.connect(model=MODEL, config=betty_config) as betty,
            client.aio.live.connect(model=MODEL, config=driver_config) as driver_session,
        ):
            # Inject fatigue camera video frames into Betty's session
            if trigger_type in ("fatigue_camera", "erratic_driving"):
                event_key = trigger_data.get("fatigue_event_type") or trigger_data.get("erratic_sub_type", "")
                sev = trigger_data.get("severity")
                frames = extract_frames(event_key, sev, target_fps=1.0, driver_id=driver_id)
                if frames:
                    logger.info("Injecting %d video frames into Betty's session", len(frames))
                    for frame_bytes in frames:
                        await betty.send_realtime_input(
                            video={"data": frame_bytes, "mime_type": "image/jpeg"},
                        )
                        await asyncio.sleep(0.1)  # small gap between frames
                    logger.info("Video frames injected")

            if trigger_type == "driver_initiated":
                # Driver is calling Betty — prompt driver to initiate
                await driver_session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text="You're calling Betty. Say hello to her.")],
                    ),
                    turn_complete=True,
                )
            else:
                # Betty is calling the driver — prompt driver to answer
                await driver_session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text="Your phone is ringing. Pick it up.")],
                    ),
                    turn_complete=True,
                )

            while turn_count < MAX_TURNS and (time.time() - t0) < MAX_DURATION_S:
                if cancel_event.is_set():
                    logger.info("Simulated call cancelled by user")
                    break

                turn_count += 1
                if turn_count % 2 == 1:
                    speaker, source, target = driver["first_name"], driver_session, betty
                else:
                    speaker, source, target = "Betty", betty, driver_session

                is_driver_turn = speaker != "Betty"
                logger.info("Sim turn %d: %s speaking...", turn_count, speaker)

                has_audio, noise_cursor = await asyncio.wait_for(
                    _stream_turn(source, target, speaker,
                                 on_transcript, on_audio, t0, cancel_event,
                                 audio_segments,
                                 is_driver=is_driver_turn,
                                 noise_cursor=noise_cursor),
                    timeout=60,
                )

                if not has_audio:
                    logger.warning("Sim turn %d: no audio from %s", turn_count, speaker)
                    break

                logger.info("Sim turn %d: %s done", turn_count, speaker)

    except asyncio.CancelledError:
        logger.info("Simulated call task cancelled for %s", driver_id)
    except Exception:
        logger.exception("Error in simulated call for %s", driver_id)
    finally:
        # Save recording
        recording_path = _save_recording(audio_segments, driver_id, trigger_type, t0)
        if recording_path:
            logger.info("Call recording: %s", recording_path)

        # Save conversation memory
        if transcript_entries:
            # Build a brief summary from transcript
            betty_lines = [e["text"] for e in transcript_entries if e["speaker"] == "Betty"]
            driver_lines = [e["text"] for e in transcript_entries
                           if e["speaker"] != "Betty"]
            summary = (
                f"Called {driver['first_name']} ({trigger_type}). "
                f"Driver said: {' '.join(driver_lines[:20])[:200]}. "
                f"Betty said: {' '.join(betty_lines[:20])[:200]}"
            )
            # Infer fatigue from trigger
            fatigue = "alert"
            if trigger_type == "fatigue_camera":
                sev = trigger_data.get("severity", "low")
                fatigue = {"high": "fatigued", "medium": "mildly_tired"}.get(sev, "alert")
            action = "encouraged_break" if trigger_type in ("fatigue_camera", "break_limit") else "none"

            try:
                add_memory_entry(
                    driver_id=driver_id,
                    summary=summary[:500],
                    fatigue_assessment=fatigue,
                    action_taken=action,
                )
            except Exception:
                logger.exception("Failed to save memory for %s", driver_id)

        call_manager.end_call(driver_id)
        duration = time.time() - t0
        await call_manager.broadcast_to_dashboard({
            "type": "call_ended",
            "driver_id": driver_id,
            "simulated": True,
        })
        logger.info("Simulated call ended: %d turns in %.1fs", turn_count, duration)

    return {
        "status": "completed",
        "call_id": call.call_id,
        "turns": turn_count,
        "duration": round(time.time() - t0, 1),
        "transcript": transcript_entries,
    }
