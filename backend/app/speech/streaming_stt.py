"""
app/speech/streaming_stt.py

Streaming Speech-to-Text service for Zigma Voice Gmail Agent.

Pipeline:

    Browser
        |
        | PCM S16LE
        | mono
        | 16 kHz
        v
    FastAPI /ws/voice
        |
        v
    StreamingSTTService
        |
        | base64 PCM
        v
    Sarvam WebSocket
        |
        v
    Saaras v3
        |
        +---- VAD
        |
        +---- transcript
        |
        v
    STTResult
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.parse import urlencode

from websockets import connect
from websockets.exceptions import (
    ConnectionClosed,
    ConnectionClosedError,
    ConnectionClosedOK,
)

from app.config.settings import get_settings


logger = logging.getLogger(__name__)

settings = get_settings()


# ============================================================================
# Constants
# ============================================================================

DEFAULT_SAMPLE_RATE = 16000

DEFAULT_MODEL = "saaras:v3"

SARVAM_WS_URL = (
    "wss://api.sarvam.ai/speech-to-text/ws"
)

# Maximum time we wait after END_SPEECH for a final transcript
# that may still be travelling from Sarvam.
FINAL_TRANSCRIPT_WAIT_SECONDS = 1.0


# ============================================================================
# Languages
# ============================================================================

LANGUAGE_CODES: dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "bn": "bn-IN",
    "gu": "gu-IN",
    "mr": "mr-IN",
    "od": "od-IN",
    "pa": "pa-IN",
    "as": "as-IN",
    "ur": "ur-IN",
    "ne": "ne-IN",
    "kok": "kok-IN",
    "ks": "ks-IN",
    "sd": "sd-IN",
    "sa": "sa-IN",
    "sat": "sat-IN",
    "mni": "mni-IN",
    "brx": "brx-IN",
    "mai": "mai-IN",
    "doi": "doi-IN",
}


LANGUAGE_ALIASES: dict[str, str] = {
    "english": "en",
    "hindi": "hi",
    "tamil": "ta",
    "telugu": "te",
    "kannada": "kn",
    "malayalam": "ml",
    "bengali": "bn",
    "gujarati": "gu",
    "marathi": "mr",
    "odia": "od",
    "oriya": "od",
    "punjabi": "pa",
    "assamese": "as",
    "urdu": "ur",
    "nepali": "ne",
    "konkani": "kok",
    "kashmiri": "ks",
    "sindhi": "sd",
    "sanskrit": "sa",
    "santali": "sat",
    "manipuri": "mni",
    "bodo": "brx",
    "maithili": "mai",
    "dogri": "doi",
    "auto": "unknown",
    "automatic": "unknown",
    "detect": "unknown",
    "unknown": "unknown",
}


# ============================================================================
# STT result
# ============================================================================

@dataclass
class STTResult:
    transcript: str = ""

    language: str | None = None

    language_code: str | None = None

    request_id: str | None = None

    audio_duration: float | None = None

    processing_latency: float | None = None

    is_final: bool = False

    vad_signal: str | None = None

    raw: object | None = None


# ============================================================================
# Service
# ============================================================================

class StreamingSTTService:

    def __init__(self) -> None:

        self.provider = (
            getattr(
                settings,
                "stt_provider",
                None,
            )
            or "sarvam"
        ).strip().lower()

        self.model = (
            getattr(
                settings,
                "sarvam_stt_model",
                None,
            )
            or DEFAULT_MODEL
        ).strip()

        self.api_key = (
            getattr(
                settings,
                "sarvam_api_key",
                None,
            )
            or ""
        ).strip()

        if self.provider != "sarvam":

            raise ValueError(
                f"Unsupported STT provider: "
                f"{self.provider}"
            )

        if not self.api_key:

            raise ValueError(
                "SARVAM_API_KEY is required."
            )

        logger.info(
            "Streaming STT initialized | "
            "provider=%s | model=%s",
            self.provider,
            self.model,
        )

    # ========================================================================
    # Language normalization
    # ========================================================================

    @staticmethod
    def normalize_language(
        language: str | None,
    ) -> str:

        if not language:
            return "unknown"

        value = str(
            language
        ).strip().lower()

        if not value:
            return "unknown"

        value = LANGUAGE_ALIASES.get(
            value,
            value,
        )

        if value == "unknown":
            return "unknown"

        # Already BCP-47.
        for code in LANGUAGE_CODES.values():

            if value == code.lower():

                return code

        # Short language code.
        if value in LANGUAGE_CODES:

            return LANGUAGE_CODES[value]

        logger.warning(
            "Unsupported language '%s'. "
            "Falling back to automatic detection.",
            language,
        )

        return "unknown"

    # ========================================================================
    # Build Sarvam WebSocket URL
    # ========================================================================

    def _build_ws_url(
        self,
        language_code: str,
        sample_rate: int,
        mode: str,
    ) -> str:

        params = {
            "language-code": language_code,
            "model": self.model,
            "mode": mode,
            "sample_rate": str(
                sample_rate
            ),
            "input_audio_codec": "pcm_s16le",
            "high_vad_sensitivity": "true",
            "vad_signals": "true",
            "flush_signal": "true",
        }

        return (
            SARVAM_WS_URL
            + "?"
            + urlencode(params)
        )

    # ========================================================================
    # Connection state
    # ========================================================================

    @staticmethod
    def _is_open(
        websocket: Any,
    ) -> bool:

        """
        Compatible with modern websockets versions.

        Modern websockets exposes connection state through:

            websocket.state

        rather than relying on websocket.closed.
        """

        try:

            state = getattr(
                websocket,
                "state",
                None,
            )

            if state is None:

                return True

            state_string = str(
                state
            ).lower()

            return state_string not in {
                "closed",
                "3",
            }

        except Exception:

            return True

    # ========================================================================
    # Send PCM
    # ========================================================================

    async def _send_pcm_audio(
        self,
        websocket: Any,
        pcm_data: bytes,
        sample_rate: int,
    ) -> None:

        if not pcm_data:
            return

        if not self._is_open(
            websocket
        ):
            return

        encoded_audio = (
            base64.b64encode(
                pcm_data
            ).decode(
                "ascii"
            )
        )

        message = {
            "audio": {
                "data": encoded_audio,

                "sample_rate": str(
                    sample_rate
                ),

                # Sarvam's streaming API accepts
                # raw PCM through input_audio_codec=pcm_s16le.
                #
                # The message itself uses audio/wav
                # as required by the WebSocket message
                # structure.
                "encoding": "audio/wav",
            }
        }

        await websocket.send(
            json.dumps(
                message
            )
        )

    # ========================================================================
    # Flush
    # ========================================================================

    async def _send_flush(
        self,
        websocket: Any,
    ) -> None:

        if not self._is_open(
            websocket
        ):

            return

        await websocket.send(
            json.dumps(
                {
                    "type": "flush"
                }
            )
        )

    # ========================================================================
    # Decode Sarvam response
    # ========================================================================

    @staticmethod
    def _decode_message(
        message: Any,
    ) -> dict[str, Any] | None:

        if message is None:

            return None

        if isinstance(
            message,
            bytes,
        ):

            try:

                message = message.decode(
                    "utf-8"
                )

            except UnicodeDecodeError:

                logger.warning(
                    "Received non-UTF8 "
                    "binary response from Sarvam."
                )

                return None

        if isinstance(
            message,
            str,
        ):

            try:

                data = json.loads(
                    message
                )

            except json.JSONDecodeError:

                logger.warning(
                    "Invalid JSON from Sarvam: %r",
                    message,
                )

                return None

        elif isinstance(
            message,
            dict,
        ):

            data = message

        else:

            logger.warning(
                "Unexpected Sarvam message type: %s",
                type(message),
            )

            return None

        if not isinstance(
            data,
            dict,
        ):

            return None

        return data

    # ========================================================================
    # Get nested data
    # ========================================================================

    @staticmethod
    def _data(
        response: dict[str, Any],
    ) -> dict[str, Any]:

        data = response.get(
            "data"
        )

        if isinstance(
            data,
            dict,
        ):

            return data

        return response

    # ========================================================================
    # VAD
    # ========================================================================

    @classmethod
    def _extract_vad_signal(
        cls,
        response: dict[str, Any],
    ) -> str | None:

        data = cls._data(
            response
        )

        signal = (
            data.get(
                "signal_type"
            )
            or data.get(
                "event_type"
            )
            or response.get(
                "signal_type"
            )
            or response.get(
                "event_type"
            )
        )

        if not signal:

            return None

        signal = str(
            signal
        ).strip().upper()

        if signal in {
            "START_SPEECH",
            "END_SPEECH",
        }:

            return signal

        return None

    # ========================================================================
    # Transcript
    # ========================================================================

    @classmethod
    def _extract_transcript(
        cls,
        response: dict[str, Any],
    ) -> str:

        data = cls._data(
            response
        )

        transcript = (
            data.get(
                "transcript"
            )
        )

        if transcript is None:

            transcript = (
                response.get(
                    "transcript"
                )
            )

        if transcript is None:

            return ""

        return str(
            transcript
        ).strip()

    # ========================================================================
    # Metadata
    # ========================================================================

    @classmethod
    def _extract_metadata(
        cls,
        response: dict[str, Any],
    ) -> dict[str, Any]:

        data = cls._data(
            response
        )

        metrics = data.get(
            "metrics"
        )

        if not isinstance(
            metrics,
            dict,
        ):

            metrics = {}

        return {
            "request_id": (
                data.get(
                    "request_id"
                )
                or response.get(
                    "request_id"
                )
            ),

            "language": (
                data.get(
                    "language"
                )
                or response.get(
                    "language"
                )
            ),

            "language_code": (
                data.get(
                    "language_code"
                )
                or response.get(
                    "language_code"
                )
            ),

            "audio_duration": (
                metrics.get(
                    "audio_duration"
                )
            ),

            "processing_latency": (
                metrics.get(
                    "processing_latency"
                )
            ),
        }

    # ========================================================================
    # Detect whether Sarvam response is final
    # ========================================================================

    @classmethod
    def _is_response_final(
        cls,
        response: dict[str, Any],
    ) -> bool:

        data = cls._data(
            response
        )

        return bool(
            data.get(
                "is_final"
            )
            or data.get(
                "final"
            )
            or data.get(
                "transcript_final"
            )
            or response.get(
                "is_final"
            )
            or response.get(
                "final"
            )
            or response.get(
                "transcript_final"
            )
        )

    # ========================================================================
    # Stream audio
    # ========================================================================

    async def stream_audio(
        self,
        audio_stream: AsyncIterator[bytes],
        language: str | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        mode: str = "transcribe",
    ) -> AsyncIterator[STTResult]:

        """
        Stream browser PCM audio to Sarvam and yield STTResult objects.

        Important:

        The browser connection remains open continuously.

        Therefore:

            audio_stream does NOT determine utterance boundaries.

        Sarvam VAD determines:

            START_SPEECH
            END_SPEECH

        Each END_SPEECH completes one voice command.

        The WebSocket is flushed only when the local audio stream itself
        finishes, such as when the browser disconnects.
        """

        language_code = (
            self.normalize_language(
                language
            )
        )

        ws_url = self._build_ws_url(
            language_code=language_code,
            sample_rate=sample_rate,
            mode=mode,
        )

        logger.info(
            "Connecting to Sarvam STT | "
            "url=%s | model=%s | language=%s | "
            "sample_rate=%s | codec=pcm_s16le",
            SARVAM_WS_URL,
            self.model,
            language_code,
            sample_rate,
        )

        sender_task: asyncio.Task | None = None

        # ====================================================================
        # Utterance state
        # ====================================================================

        current_transcript = ""

        current_language: str | None = None

        current_language_code: str | None = None

        current_request_id: str | None = None

        current_audio_duration: float | None = None

        current_processing_latency: float | None = None

        speech_started = False

        speech_ended = False

        final_sent = False

        # ====================================================================
        # Reset utterance
        # ====================================================================

        def reset_utterance() -> None:

            nonlocal current_transcript
            nonlocal current_language
            nonlocal current_language_code
            nonlocal current_request_id
            nonlocal current_audio_duration
            nonlocal current_processing_latency
            nonlocal speech_started
            nonlocal speech_ended
            nonlocal final_sent

            current_transcript = ""

            current_language = None

            current_language_code = None

            current_request_id = None

            current_audio_duration = None

            current_processing_latency = None

            speech_started = False

            speech_ended = False

            final_sent = False

        # ====================================================================
        # Build result
        # ====================================================================

        def build_result(
            *,
            is_final: bool,
            vad_signal: str | None = None,
            raw: object | None = None,
        ) -> STTResult:

            return STTResult(
                transcript=current_transcript,
                language=current_language,
                language_code=current_language_code,
                request_id=current_request_id,
                audio_duration=current_audio_duration,
                processing_latency=current_processing_latency,
                is_final=is_final,
                vad_signal=vad_signal,
                raw=raw,
            )

        # ====================================================================
        # Finalize current utterance
        # ====================================================================

        def finalize_current_utterance(
            raw: object | None = None,
            vad_signal: str | None = None,
        ) -> STTResult | None:

            nonlocal final_sent

            if final_sent:

                return None

            final_text = (
                current_transcript
                .strip()
            )

            if not final_text:

                return None

            final_sent = True

            logger.info(
                "FINAL SARVAM TRANSCRIPT: %s",
                final_text,
            )

            return build_result(
                is_final=True,
                vad_signal=vad_signal,
                raw=raw,
            )

        # ====================================================================
        # Connect to Sarvam
        # ====================================================================

        try:

            # ----------------------------------------------------------------
            # IMPORTANT:
            #
            # The previous implementation accidentally used:
            #
            #     sarvam_ws_url
            #     api_key
            #
            # Neither variable existed in this method.
            #
            # We now correctly use:
            #
            #     ws_url
            #     self.api_key
            #
            # ----------------------------------------------------------------

            try:

                websocket_context = connect(
                    ws_url,
                    additional_headers={
                        "Api-Subscription-Key": (
                            self.api_key
                        )
                    },

                    # --------------------------------------------------------
                    # Sarvam may not respond to the automatic WebSocket
                    # keepalive ping in the way expected by the client.
                    #
                    # Browser audio itself keeps the connection active.
                    # --------------------------------------------------------

                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                )

            except TypeError:

                # ------------------------------------------------------------
                # Compatibility with older websockets versions where the
                # header argument is named extra_headers.
                # ------------------------------------------------------------

                logger.info(
                    "Using legacy websockets "
                    "extra_headers compatibility mode."
                )

                websocket_context = connect(
                    ws_url,
                    extra_headers={
                        "Api-Subscription-Key": (
                            self.api_key
                        )
                    },
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                )

            async with websocket_context as websocket:

                logger.info(
                    "CONNECTED TO SARVAM STT"
                )

                # =============================================================
                # Sender
                # =============================================================

                async def sender() -> None:

                    try:

                        async for chunk in audio_stream:

                            if not chunk:

                                continue

                            if not isinstance(
                                chunk,
                                bytes,
                            ):

                                logger.warning(
                                    "Ignoring non-bytes "
                                    "audio: %s",
                                    type(chunk),
                                )

                                continue

                            if not self._is_open(
                                websocket
                            ):

                                logger.info(
                                    "Sarvam socket is closed; "
                                    "stopping sender."
                                )

                                break

                            logger.debug(
                                "Sending PCM to Sarvam: "
                                "%d bytes",
                                len(chunk),
                            )

                            try:

                                await self._send_pcm_audio(
                                    websocket,
                                    chunk,
                                    sample_rate,
                                )

                            except (
                                ConnectionClosed,
                                ConnectionClosedError,
                                ConnectionClosedOK,
                            ):

                                logger.info(
                                    "Sarvam connection closed "
                                    "while sending audio."
                                )

                                break

                    except asyncio.CancelledError:

                        raise

                    except Exception:

                        logger.exception(
                            "Sarvam sender failed."
                        )

                        raise

                    finally:

                        # -----------------------------------------------------
                        # Only flush when the complete browser audio stream
                        # ends.
                        #
                        # Normal speech turns are finalized by Sarvam VAD.
                        # -----------------------------------------------------

                        try:

                            if self._is_open(
                                websocket
                            ):

                                await self._send_flush(
                                    websocket
                                )

                                logger.info(
                                    "Sent Sarvam FLUSH "
                                    "because audio stream ended."
                                )

                        except Exception:

                            logger.debug(
                                "Sarvam flush skipped "
                                "because connection closed.",
                                exc_info=True,
                            )

                sender_task = asyncio.create_task(
                    sender()
                )

                # =============================================================
                # Receiver
                # =============================================================

                try:

                    while True:

                        try:

                            raw_message = (
                                await websocket.recv()
                            )

                        except ConnectionClosedOK as exc:

                            logger.info(
                                "Sarvam WebSocket closed normally: %s",
                                exc,
                            )

                            break

                        except ConnectionClosedError as exc:

                            logger.warning(
                                "Sarvam WebSocket closed with error: %s",
                                exc,
                            )

                            break

                        except ConnectionClosed as exc:

                            logger.warning(
                                "Sarvam WebSocket closed: %s",
                                exc,
                            )

                            break

                        response = (
                            self._decode_message(
                                raw_message
                            )
                        )

                        if response is None:

                            continue

                        logger.debug(
                            "SARVAM RESPONSE: %s",
                            response,
                        )

                        # -----------------------------------------------------
                        # Response type
                        # -----------------------------------------------------

                        response_type = (
                            response.get(
                                "type"
                            )
                        )

                        # =====================================================
                        # Error
                        # =====================================================

                        if response_type == "error":

                            logger.error(
                                "SARVAM STT ERROR: %s",
                                response,
                            )

                            yield STTResult(
                                transcript="",
                                is_final=False,
                                raw=response,
                            )

                            continue

                        # =====================================================
                        # Metadata
                        # =====================================================

                        metadata = (
                            self._extract_metadata(
                                response
                            )
                        )

                        if metadata.get(
                            "language"
                        ):

                            current_language = (
                                metadata.get(
                                    "language"
                                )
                            )

                        if metadata.get(
                            "language_code"
                        ):

                            current_language_code = (
                                metadata.get(
                                    "language_code"
                                )
                            )

                        if metadata.get(
                            "request_id"
                        ):

                            current_request_id = (
                                metadata.get(
                                    "request_id"
                                )
                            )

                        if metadata.get(
                            "audio_duration"
                        ) is not None:

                            current_audio_duration = (
                                metadata.get(
                                    "audio_duration"
                                )
                            )

                        if metadata.get(
                            "processing_latency"
                        ) is not None:

                            current_processing_latency = (
                                metadata.get(
                                    "processing_latency"
                                )
                            )

                        # =====================================================
                        # VAD
                        # =====================================================

                        vad_signal = (
                            self._extract_vad_signal(
                                response
                            )
                        )

                        if vad_signal:

                            logger.info(
                                "SARVAM VAD: %s",
                                vad_signal,
                            )

                        # =====================================================
                        # START_SPEECH
                        # =====================================================

                        if (
                            vad_signal
                            == "START_SPEECH"
                        ):

                            # -------------------------------------------------
                            # New utterance.
                            #
                            # Anything from the previous utterance has already
                            # been finalized.
                            # -------------------------------------------------

                            reset_utterance()

                            speech_started = True

                            logger.info(
                                "NEW VOICE UTTERANCE STARTED"
                            )

                            yield STTResult(
                                transcript="",
                                language=(
                                    current_language
                                ),
                                language_code=(
                                    current_language_code
                                ),
                                request_id=(
                                    current_request_id
                                ),
                                audio_duration=(
                                    current_audio_duration
                                ),
                                processing_latency=(
                                    current_processing_latency
                                ),
                                is_final=False,
                                vad_signal="START_SPEECH",
                                raw=response,
                            )

                            continue

                        # =====================================================
                        # Transcript
                        # =====================================================

                        transcript = (
                            self._extract_transcript(
                                response
                            )
                        )

                        if transcript:

                            # -------------------------------------------------
                            # IMPORTANT:
                            #
                            # Sarvam's streaming transcript is treated as the
                            # current hypothesis, not something to append.
                            #
                            # Example:
                            #
                            # "show"
                            # "show me"
                            # "show me today's emails"
                            #
                            # We keep only the latest transcript.
                            # -------------------------------------------------

                            current_transcript = (
                                transcript
                            )

                            logger.info(
                                "SARVAM TRANSCRIPT: %s",
                                current_transcript,
                            )

                            response_final = (
                                self._is_response_final(
                                    response
                                )
                            )

                            # -------------------------------------------------
                            # If Sarvam explicitly marks this response final,
                            # immediately emit it.
                            # -------------------------------------------------

                            if (
                                response_final
                                and not final_sent
                            ):

                                final_result = (
                                    finalize_current_utterance(
                                        raw=response,
                                        vad_signal=(
                                            vad_signal
                                        ),
                                    )
                                )

                                if final_result:

                                    yield final_result

                                continue

                            # -------------------------------------------------
                            # If VAD already said END_SPEECH and the transcript
                            # arrived afterward, finalize it now.
                            #
                            # This fixes the race where END_SPEECH arrives
                            # before the final transcript message.
                            # -------------------------------------------------

                            if (
                                speech_ended
                                and not final_sent
                            ):

                                final_result = (
                                    finalize_current_utterance(
                                        raw=response,
                                        vad_signal=(
                                            "END_SPEECH"
                                        ),
                                    )
                                )

                                if final_result:

                                    yield final_result

                                    continue

                            # -------------------------------------------------
                            # Otherwise send it as interim.
                            # -------------------------------------------------

                            yield build_result(
                                is_final=False,
                                vad_signal=(
                                    vad_signal
                                ),
                                raw=response,
                            )

                        # =====================================================
                        # END_SPEECH
                        # =====================================================

                        if (
                            vad_signal
                            == "END_SPEECH"
                        ):

                            speech_ended = True

                            # -------------------------------------------------
                            # If we already have a transcript, finalize now.
                            # -------------------------------------------------

                            if (
                                current_transcript
                                and not final_sent
                            ):

                                final_result = (
                                    finalize_current_utterance(
                                        raw=response,
                                        vad_signal=(
                                            "END_SPEECH"
                                        ),
                                    )
                                )

                                if final_result:

                                    yield final_result

                                continue

                            # -------------------------------------------------
                            # No transcript yet.
                            #
                            # Do NOT emit an empty final transcript.
                            #
                            # The transcript may arrive immediately after the
                            # VAD END_SPEECH event.
                            # -------------------------------------------------

                            logger.info(
                                "END_SPEECH received "
                                "without transcript; "
                                "waiting for final transcript."
                            )

                            continue

                        # =====================================================
                        # Flush / completion
                        # =====================================================

                        if (
                            response_type
                            in {
                                "flush",
                                "done",
                                "completion",
                                "completed",
                            }
                        ):

                            if (
                                current_transcript
                                and not final_sent
                            ):

                                final_result = (
                                    finalize_current_utterance(
                                        raw=response,
                                        vad_signal=(
                                            vad_signal
                                        ),
                                    )
                                )

                                if final_result:

                                    yield final_result

                                continue

                finally:

                    # ---------------------------------------------------------
                    # Stop sender
                    # ---------------------------------------------------------

                    if (
                        sender_task is not None
                        and not sender_task.done()
                    ):

                        sender_task.cancel()

                    if sender_task is not None:

                        try:

                            await sender_task

                        except asyncio.CancelledError:

                            pass

                        except Exception:

                            logger.debug(
                                "Sender cleanup failed.",
                                exc_info=True,
                            )

        except asyncio.CancelledError:

            logger.info(
                "Sarvam STT task cancelled."
            )

            raise

        except Exception:

            logger.exception(
                "Sarvam STT WebSocket failed."
            )

            raise

    # ========================================================================
    # Compatibility helper
    # ========================================================================

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        language: str | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        mode: str = "transcribe",
    ) -> AsyncIterator[STTResult]:

        async for result in self.stream_audio(
            audio_stream=audio_stream,
            language=language,
            sample_rate=sample_rate,
            mode=mode,
        ):

            yield result


# ============================================================================
# Shared service instance
# ============================================================================

streaming_stt = StreamingSTTService()