"""Gemini Live API session wrapper for bidirectional audio streaming.

Replaces the 653-line nova_sonic.py with a clean wrapper
around the google-genai SDK's Live API.
"""

import asyncio
import logging
import os
from typing import Any, Callable, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiLiveSession:
    """Wraps a Gemini Live API session for bidirectional voice streaming."""

    def __init__(
        self,
        system_prompt: str,
        voice: str = "Aoede",
        model: str = "gemini-2.5-flash-native-audio-latest",
        tools: Optional[list[types.FunctionDeclaration]] = None,
        tool_handler: Optional[Callable] = None,
        on_audio: Optional[Callable[[bytes], Any]] = None,
        on_text: Optional[Callable[[str], Any]] = None,
        on_input_text: Optional[Callable[[str], Any]] = None,
        on_turn_complete: Optional[Callable[[], Any]] = None,
        on_interrupted: Optional[Callable[[], Any]] = None,
    ):
        self.system_prompt = system_prompt
        self.voice = voice
        self.model = model
        self.tools = tools or []
        self.tool_handler = tool_handler
        self.on_audio = on_audio
        self.on_text = on_text
        self.on_input_text = on_input_text
        self.on_turn_complete = on_turn_complete
        self.on_interrupted = on_interrupted
        self._session = None
        self._client = None
        self._connection = None  # async context manager
        self._receive_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Establish connection to Gemini Live API."""
        api_key = os.environ.get("GEMINI_API_KEY", "")
        self._client = genai.Client(api_key=api_key)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice,
                    )
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=self.system_prompt)]
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                    silence_duration_ms=500,
                    prefix_padding_ms=200,
                ),
            ),
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        if self.tools:
            config.tools = [types.Tool(function_declarations=self.tools)]

        self._connection = self._client.aio.live.connect(
            model=self.model, config=config
        )
        self._session = await self._connection.__aenter__()
        logger.info("Gemini Live session connected (voice=%s)", self.voice)

    async def send_audio(self, pcm_data: bytes) -> None:
        """Send raw PCM audio to Gemini (16-bit, 16kHz, mono)."""
        if not self._session:
            return
        await self._session.send_realtime_input(
            audio={"data": pcm_data, "mime_type": "audio/pcm"},
        )

    async def send_activity_start(self) -> None:
        """Signal that the user has started speaking."""
        if not self._session:
            return
        await self._session.send_realtime_input(
            activity_start=types.ActivityStart(),
        )

    async def send_activity_end(self) -> None:
        """Signal that the user has stopped speaking."""
        if not self._session:
            return
        await self._session.send_realtime_input(
            activity_end=types.ActivityEnd(),
        )

    async def send_video_frame(self, jpeg_bytes: bytes) -> None:
        """Send a video frame (JPEG) to Gemini."""
        if not self._session:
            return
        await self._session.send_realtime_input(
            video={"data": jpeg_bytes, "mime_type": "image/jpeg"},
        )

    async def send_text(self, text: str) -> None:
        """Send a text message (e.g., speaks-first prompt)."""
        if not self._session:
            return
        await self._session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text=text)],
            ),
            turn_complete=True,
        )

    async def receive_loop(self) -> None:
        """Process responses from Gemini. Run as an asyncio task.

        Uses Google's recommended pattern: each session.receive() call
        yields responses for one turn. When a turn is interrupted (user
        barge-in), the inner loop ends and we notify via on_interrupted
        so the caller can clear any buffered playback audio.
        """
        if not self._session:
            return
        try:
            while True:
                turn = self._session.receive()
                async for response in turn:
                    server_content = response.server_content
                    tool_call = response.tool_call

                    if server_content:
                        if server_content.model_turn and server_content.model_turn.parts:
                            for part in server_content.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    if self.on_audio:
                                        await _maybe_await(self.on_audio(part.inline_data.data))

                        # Betty's speech transcript
                        ot = getattr(server_content, 'output_transcription', None)
                        if ot and ot.text:
                            if self.on_text:
                                await _maybe_await(self.on_text(ot.text))

                        # Driver's speech transcript (input audio transcription)
                        it = getattr(server_content, 'input_transcription', None)
                        if it and it.text:
                            if self.on_input_text:
                                await _maybe_await(self.on_input_text(it.text))

                        if server_content.turn_complete:
                            if self.on_turn_complete:
                                await _maybe_await(self.on_turn_complete())

                    if tool_call and self.tool_handler:
                        results = []
                        for fc in tool_call.function_calls:
                            logger.info("Tool call: %s(%s)", fc.name, fc.args)
                            result = await self.tool_handler(fc.name, fc.args or {})
                            results.append(
                                types.FunctionResponse(
                                    name=fc.name,
                                    id=fc.id,
                                    response=result,
                                )
                            )
                        await self._session.send_tool_response(function_responses=results)

                # Turn ended (interrupted by user or completed) — clear stale audio
                logger.debug("Turn iteration ended, signalling interruption clear")
                if self.on_interrupted:
                    await _maybe_await(self.on_interrupted())

        except asyncio.CancelledError:
            logger.info("Receive loop cancelled")
        except Exception:
            logger.exception("Error in receive loop")

    def start_receiving(self) -> asyncio.Task:
        """Start the receive loop as a background task."""
        self._receive_task = asyncio.create_task(self.receive_loop())
        return self._receive_task

    async def close(self) -> None:
        """Close the Gemini session."""
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._connection:
            await self._connection.__aexit__(None, None, None)
            logger.info("Gemini Live session closed")


async def _maybe_await(result):
    """Await if the result is a coroutine, otherwise return as-is."""
    if asyncio.iscoroutine(result):
        return await result
    return result
