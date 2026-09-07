from __future__ import annotations

import base64
import logging
from typing import AsyncGenerator, Optional

from sarvamai import AsyncSarvamAI
from sarvamai.types.audio_output import AudioOutput
from sarvamai.types.error_response import ErrorResponse
from sarvamai.types.event_response import EventResponse

from app.config.settings import get_settings


logger = logging.getLogger(__name__)


class StreamingTTSService:
    """
    Streaming Text-to-Speech service using Sarvam Bulbul.

    Text
      ↓
    Sarvam WebSocket
      ↓
    AudioOutput chunks
      ↓
    Decoded audio bytes

    Language is supplied dynamically by the voice pipeline.

    Supported examples:

        en-IN → English
        hi-IN → Hindi
        te-IN → Telugu
        ta-IN → Tamil
        kn-IN → Kannada
        ml-IN → Malayalam

    The language is NOT hard-coded.
    """

    def __init__(self) -> None:

        self.settings = get_settings()

        if not self.settings.sarvam_api_key:
            raise ValueError(
                "SARVAM_API_KEY is not configured."
            )

        self.client = AsyncSarvamAI(
            api_subscription_key=(
                self.settings.sarvam_api_key
            )
        )

    # =========================================================
    # Stream TTS
    # =========================================================

    async def stream(
        self,
        text: str,
        language_code: Optional[str] = None,
        speaker: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesized audio.

        Language is resolved in this order:

            1. language_code supplied by caller
            2. SARVAM_TTS_LANGUAGE_CODE from settings

        The caller should normally provide the detected/requested
        language dynamically.
        """

        # -----------------------------------------------------
        # Validate text
        # -----------------------------------------------------

        if not text or not text.strip():

            logger.warning(
                "TTS received empty text."
            )

            return

        # -----------------------------------------------------
        # Resolve language
        # -----------------------------------------------------

        language = (
            language_code
            or self.settings.sarvam_tts_language_code
        )

        if not language:

            raise ValueError(
                "Sarvam TTS language_code is not configured."
            )

        language = str(
            language
        ).strip()

        if not language:

            raise ValueError(
                "Sarvam TTS language_code is empty."
            )

        # -----------------------------------------------------
        # Resolve speaker
        # -----------------------------------------------------

        voice = (
            speaker
            or self.settings.sarvam_tts_speaker
            or "anushka"
        )

        voice = str(
            voice
        ).strip()

        # -----------------------------------------------------
        # Resolve model
        # -----------------------------------------------------

        model = (
            self.settings.sarvam_tts_model
            or "bulbul:v3"
        )

        logger.info(
            "Starting Sarvam streaming TTS: "
            "model=%s language=%s speaker=%s",
            model,
            language,
            voice,
        )

        try:

            # -------------------------------------------------
            # Connect to Sarvam WebSocket
            # -------------------------------------------------

            async with (
                self.client
                .text_to_speech_streaming
                .connect(
                    model=model,
                    send_completion_event="true",
                )
                as ws
            ):

                # -------------------------------------------------
                # IMPORTANT:
                #
                # sarvamai==0.1.30 expects:
                #
                # target_language_code
                #
                # NOT:
                #
                # language_code
                # -------------------------------------------------

                await ws.configure(
                    target_language_code=language,
                    speaker=voice,
                    pace=1.0,
                    speech_sample_rate=24000,
                    enable_preprocessing=True,
                    output_audio_codec="mp3",
                    output_audio_bitrate="128k",
                    min_buffer_size=50,
                    max_chunk_length=150,
                )

                # -------------------------------------------------
                # Send text
                # -------------------------------------------------

                await ws.convert(
                    text.strip()
                )

                # -------------------------------------------------
                # Flush remaining buffered text
                # -------------------------------------------------

                await ws.flush()

                # -------------------------------------------------
                # Receive streaming responses
                # -------------------------------------------------

                async for message in ws:

                    # =============================================
                    # Audio
                    # =============================================

                    if isinstance(
                        message,
                        AudioOutput,
                    ):

                        audio_data = (
                            message.data.audio
                        )

                        if not audio_data:
                            continue

                        try:

                            audio_chunk = (
                                base64.b64decode(
                                    audio_data
                                )
                            )

                        except Exception as exc:

                            logger.exception(
                                "Failed to decode Sarvam "
                                "audio chunk: %s",
                                exc,
                            )

                            continue

                        if audio_chunk:

                            yield audio_chunk

                    # =============================================
                    # Completion event
                    # =============================================

                    elif isinstance(
                        message,
                        EventResponse,
                    ):

                        event_type = (
                            message.data.event_type
                        )

                        logger.debug(
                            "Sarvam TTS event: %s",
                            event_type,
                        )

                        if event_type == "final":

                            logger.info(
                                "Sarvam TTS generation "
                                "completed."
                            )

                            break

                    # =============================================
                    # Sarvam error
                    # =============================================

                    elif isinstance(
                        message,
                        ErrorResponse,
                    ):

                        error_message = (
                            message.data.message
                        )

                        logger.error(
                            "Sarvam TTS error: %s",
                            error_message,
                        )

                        raise RuntimeError(
                            "Sarvam TTS error: "
                            f"{error_message}"
                        )

                    # =============================================
                    # Unknown response
                    # =============================================

                    else:

                        logger.debug(
                            "Unknown Sarvam TTS response: %r",
                            message,
                        )

        except Exception:

            logger.exception(
                "Sarvam streaming TTS failed."
            )

            raise

        finally:

            logger.info(
                "Streaming TTS session completed."
            )