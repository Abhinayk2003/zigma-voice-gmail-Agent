
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)

from app.agent.orchestrator import (
    gmail_orchestrator,
)

from app.speech.streaming_stt import (
    STTResult,
    streaming_stt,
)

from app.speech.streaming_tts import (
    StreamingTTSService,
)


logger = logging.getLogger(__name__)

tts_service = StreamingTTSService()

router = APIRouter(
    tags=["Voice Agent"],
)


# ============================================================================
# Safe JSON sender
# ============================================================================

async def _send_json(
    websocket: WebSocket,
    payload: dict[str, Any],
) -> bool:
    """
    Safely send a JSON message over the WebSocket.

    Returns:
        True  -> message sent successfully
        False -> WebSocket is already closed or sending failed
    """

    try:

        await websocket.send_json(
            payload
        )

        return True

    except (
        WebSocketDisconnect,
        RuntimeError,
    ) as exc:

        logger.debug(
            "Unable to send WebSocket JSON message: %s",
            exc,
        )

        return False

    except Exception:

        logger.debug(
            "Unable to send WebSocket JSON message.",
            exc_info=True,
        )

        return False


# ============================================================================
# Safe audio sender
# ============================================================================

async def _send_audio(
    websocket: WebSocket,
    audio_data: bytes,
) -> bool:
    """
    Safely send binary audio over the WebSocket.

    This prevents a client disconnect during TTS from
    producing an unhandled RuntimeError.
    """

    if not audio_data:

        return False

    try:

        await websocket.send_bytes(
            audio_data
        )

        return True

    except (
        WebSocketDisconnect,
        RuntimeError,
    ) as exc:

        logger.info(
            "WebSocket closed before TTS audio "
            "could be sent: %s",
            exc,
        )

        return False

    except Exception:

        logger.exception(
            "Failed to send TTS audio."
        )

        return False


# ============================================================================
# Process agent request
# ============================================================================

async def _process_agent_request(
    websocket: WebSocket,
    user_text: str,
    account_email: str,
    language_code: str | None = None,
    generate_tts: bool = True,
) -> None:
    """
    Process one Gmail agent request.

    Flow:

        User text
             ↓
        Gmail Orchestrator
             ↓
        Response text
             ↓
        Sarvam TTS
             ↓
        WebSocket audio
    """

    user_text = (
        str(user_text)
        .strip()
    )

    if not user_text:

        return

    logger.info(
        "============================================================"
    )

    logger.info(
        "VOICE AGENT REQUEST"
    )

    logger.info(
        "ACCOUNT: %s",
        account_email,
    )

    logger.info(
        "TEXT: %s",
        user_text,
    )

    logger.info(
        "LANGUAGE CODE: %s",
        language_code or "not provided",
    )

    logger.info(
        "============================================================"
    )

    # ------------------------------------------------------------------------
    # Notify frontend that processing started
    # ------------------------------------------------------------------------

    if not await _send_json(
        websocket,
        {
            "type": "processing",
            "text": user_text,
            "language_code": language_code,
        },
    ):

        logger.info(
            "Client disconnected before agent processing started."
        )

        return

    try:

        # ====================================================================
        # Run Gmail orchestrator
        # ====================================================================

        result = await asyncio.to_thread(
            gmail_orchestrator.process,
            user_text=user_text,
            account_email=account_email,
        )

        # ====================================================================
        # Validate result
        # ====================================================================

        if not isinstance(
            result,
            dict,
        ):

            result = {
                "success": False,
                "user_message": (
                    "I couldn't process that request."
                ),
            }

        # ====================================================================
        # Debug logging
        # ====================================================================

        logger.info(
            "============================================================"
        )

        logger.info(
            "GMAIL ORCHESTRATOR RESULT"
        )

        logger.info(
            "SUCCESS: %s",
            result.get("success"),
        )

        logger.info(
            "INTENT: %s",
            result.get("intent"),
        )

        logger.info(
            "CONFIDENCE: %s",
            result.get("confidence"),
        )

        logger.info(
            "RESULT: %s",
            result.get("result"),
        )

        logger.info(
            "USER MESSAGE: %s",
            result.get("user_message"),
        )

        logger.info(
            "ERROR: %s",
            result.get("error"),
        )

        logger.info(
            "============================================================"
        )

        # ====================================================================
        # Final response text
        # ====================================================================

        response_text = (
            result.get(
                "user_message"
            )
            or result.get(
                "message"
            )
            or "Request completed."
        )

        response_text = str(
            response_text
        ).strip()

        # ====================================================================
        # Generate voice response using Sarvam TTS
        # ====================================================================

        try:

            logger.info(
                "Starting TTS generation..."
            )

            logger.info(
                "TTS LANGUAGE CODE: %s",
                language_code or "not provided",
            )

            audio_chunks: list[bytes] = []

            async for audio_chunk in tts_service.stream(
                text=response_text,
                language_code=language_code,
            ):

                if audio_chunk:

                    audio_chunks.append(
                        audio_chunk
                    )

            audio_data = b"".join(
                audio_chunks
            )

            logger.info(
                "TTS generation completed: %d bytes",
                len(audio_data),
            )

            # =================================================================
            # Send generated audio
            # =================================================================

            if audio_data:

                sent = await _send_json(
                    websocket,
                    {
                        "type": "audio_start",
                        "content_type": "audio/mpeg",
                        "language_code": language_code,
                    },
                )

                if not sent:

                    logger.info(
                        "Client disconnected before TTS audio_start."
                    )

                    return

                audio_sent = await _send_audio(
                    websocket,
                    audio_data,
                )

                if not audio_sent:

                    logger.info(
                        "Client disconnected while sending TTS audio."
                    )

                    return

                logger.info(
                    "TTS audio sent to frontend: %d bytes",
                    len(audio_data),
                )

                if not await _send_json(
                    websocket,
                    {
                        "type": "audio_end",
                    },
                ):

                    logger.info(
                        "Client disconnected before audio_end."
                    )

                    return

            else:

                logger.warning(
                    "TTS returned no audio data."
                )

        except asyncio.CancelledError:

            logger.info(
                "TTS generation cancelled."
            )

            raise

        except Exception:

            logger.exception(
                "TTS generation failed."
            )

            await _send_json(
                websocket,
                {
                    "type": "audio_error",
                    "message": (
                        "Unable to generate voice response."
                    ),
                },
            )

        # ====================================================================
        # Send text response to frontend
        # ====================================================================

        response_sent = await _send_json(
            websocket,
            {
                "type": "response",
                "text": response_text,
                "intent": result.get(
                    "intent"
                ),
                "confidence": result.get(
                    "confidence"
                ),
                "success": result.get(
                    "success",
                    False,
                ),
                "language_code": language_code,
            },
        )

        if not response_sent:

            logger.info(
                "Client disconnected before response could be sent."
            )

            return

        logger.info(
            "VOICE AGENT RESPONSE: %s",
            response_text,
        )

    except asyncio.CancelledError:

        logger.info(
            "Agent processing cancelled."
        )

        raise

    except Exception as exc:

        logger.exception(
            "Agent processing failed."
        )

        await _send_json(
            websocket,
            {
                "type": "error",
                "message": str(exc),
            },
        )


# ============================================================================
# STT result processor
# ============================================================================

async def _process_stt_results(
    websocket: WebSocket,
    audio_queue: asyncio.Queue[
        bytes | None
    ],
    account_email: str,
) -> None:
    """
    Consume microphone audio and process Sarvam STT results.

    Language detection is intentionally dynamic.

    STT:
        language=None

    Sarvam determines the language and returns:

        result.language
        result.language_code

    The detected language_code is then passed directly to
    the TTS pipeline.
    """

    async def audio_stream():

        while True:

            chunk = await audio_queue.get()

            if chunk is None:

                break

            if not isinstance(
                chunk,
                bytes,
            ):

                continue

            if not chunk:

                continue

            yield chunk

    try:

        logger.info(
            "Starting streaming STT for account: %s",
            account_email,
        )

        async for result in streaming_stt.stream_audio(
            audio_stream=audio_stream(),
            language=None,
            sample_rate=16000,
            mode="transcribe",
        ):

            if not isinstance(
                result,
                STTResult,
            ):

                continue

            # ================================================================
            # Speech started
            # ================================================================

            if result.vad_signal == "START_SPEECH":

                logger.info(
                    "VOICE SPEECH STARTED"
                )

                await _send_json(
                    websocket,
                    {
                        "type": "speech_started",
                    },
                )

                continue

            # ================================================================
            # Interim transcript
            # ================================================================

            if (
                result.transcript
                and not result.is_final
            ):

                logger.debug(
                    "INTERIM TRANSCRIPT: %s",
                    result.transcript,
                )

                await _send_json(
                    websocket,
                    {
                        "type": "interim_transcript",
                        "text": result.transcript,
                        "language": result.language,
                        "language_code": (
                            result.language_code
                        ),
                    },
                )

                continue

            # ================================================================
            # Final transcript
            # ================================================================

            if (
                result.is_final
                and result.transcript
            ):

                final_text = (
                    result.transcript
                    .strip()
                )

                if not final_text:

                    continue

                logger.info(
                    "============================================================"
                )

                logger.info(
                    "FINAL VOICE TRANSCRIPT"
                )

                logger.info(
                    "ACCOUNT: %s",
                    account_email,
                )

                logger.info(
                    "TEXT: %s",
                    final_text,
                )

                logger.info(
                    "LANGUAGE: %s",
                    result.language,
                )

                logger.info(
                    "LANGUAGE CODE: %s",
                    result.language_code,
                )

                logger.info(
                    "============================================================"
                )

                # ------------------------------------------------------------
                # Send transcript to frontend
                # ------------------------------------------------------------

                transcript_sent = await _send_json(
                    websocket,
                    {
                        "type": "transcript",
                        "text": final_text,
                        "final": True,
                        "language": result.language,
                        "language_code": (
                            result.language_code
                        ),
                        "request_id": (
                            result.request_id
                        ),
                    },
                )

                if not transcript_sent:

                    logger.info(
                        "Client disconnected after STT transcript."
                    )

                    return

                # ------------------------------------------------------------
                # ONLY final transcript goes to the agent
                #
                # The language detected by STT is passed to TTS.
                # ------------------------------------------------------------

                await _process_agent_request(
                    websocket=websocket,
                    user_text=final_text,
                    account_email=account_email,
                    language_code=result.language_code,
                )

                # ------------------------------------------------------------
                # Speech ended
                # ------------------------------------------------------------

                await _send_json(
                    websocket,
                    {
                        "type": "speech_ended",
                    },
                )

    except asyncio.CancelledError:

        logger.info(
            "Streaming STT task cancelled."
        )

        raise

    except (
        WebSocketDisconnect,
        RuntimeError,
    ) as exc:

        logger.info(
            "STT stopped because WebSocket closed: %s",
            exc,
        )

    except Exception:

        logger.exception(
            "Streaming STT processing failed."
        )

        await _send_json(
            websocket,
            {
                "type": "error",
                "message": (
                    "Speech recognition failed."
                ),
            },
        )


# ============================================================================
# Voice WebSocket
# ============================================================================

@router.websocket(
    "/ws/voice"
)
async def voice_websocket(
    websocket: WebSocket,
) -> None:

    await websocket.accept()

    logger.info(
        "============================================================"
    )

    logger.info(
        "VOICE WEBSOCKET CONNECTED"
    )

    logger.info(
        "============================================================"
    )

    # =========================================================================
    # Read authentication session
    #
    # SessionMiddleware stores the session in:
    #
    #     websocket.scope["session"]
    #
    # Do NOT use:
    #
    #     websocket.session
    # =========================================================================

    account_email: str | None = None

    session: dict[str, Any] = {}

    try:

        raw_session = websocket.scope.get(
            "session",
            {},
        )

        if isinstance(
            raw_session,
            dict,
        ):

            session = raw_session

        account_email = session.get(
            "google_account_email"
        )

    except Exception:

        logger.exception(
            "Unable to read WebSocket session."
        )

    # =========================================================================
    # Normalize account
    # =========================================================================

    if account_email:

        account_email = (
            str(account_email)
            .strip()
            .lower()
        )

    logger.info(
        "WEBSOCKET SESSION: %s",
        session,
    )

    logger.info(
        "VOICE SESSION ACCOUNT: %s",
        account_email or "NONE",
    )

    # =========================================================================
    # Authentication
    # =========================================================================

    if not account_email:

        logger.warning(
            "VOICE CONNECTION REJECTED: "
            "NO AUTHENTICATED GMAIL ACCOUNT"
        )

        await _send_json(
            websocket,
            {
                "type": "error",
                "message": (
                    "Please sign in with Google before "
                    "using the Voice Gmail Agent."
                ),
                "authenticated": False,
            },
        )

        try:

            await websocket.close(
                code=1008
            )

        except Exception:

            pass

        return

    # =========================================================================
    # Connected
    # =========================================================================

    logger.info(
        "VOICE AUTHENTICATION SUCCESSFUL"
    )

    logger.info(
        "AUTHENTICATED ACCOUNT: %s",
        account_email,
    )

    if not await _send_json(
        websocket,
        {
            "type": "connected",
            "message": (
                "Voice Gmail Agent connected."
            ),
            "authenticated": True,
            "account_email": account_email,
        },
    ):

        logger.info(
            "Client disconnected immediately after connection."
        )

        return

    # =========================================================================
    # Audio queue
    # =========================================================================

    audio_queue: asyncio.Queue[
        bytes | None
    ] = asyncio.Queue(
        maxsize=200
    )

    # =========================================================================
    # Start STT processor
    # =========================================================================

    stt_task = asyncio.create_task(
        _process_stt_results(
            websocket=websocket,
            audio_queue=audio_queue,
            account_email=account_email,
        )
    )

    try:

        while True:

            try:

                message = await websocket.receive()

            except WebSocketDisconnect:

                logger.info(
                    "VOICE CLIENT DISCONNECTED"
                )

                break

            # =================================================================
            # Disconnect
            # =================================================================

            if (
                message.get("type")
                == "websocket.disconnect"
            ):

                logger.info(
                    "VOICE CLIENT SENT DISCONNECT"
                )

                break

            # =================================================================
            # Binary audio
            # =================================================================

            audio_chunk = message.get(
                "bytes"
            )

            if audio_chunk is not None:

                if not isinstance(
                    audio_chunk,
                    bytes,
                ):

                    continue

                if not audio_chunk:

                    continue

                try:

                    audio_queue.put_nowait(
                        audio_chunk
                    )

                except asyncio.QueueFull:

                    logger.warning(
                        "Audio queue full. "
                        "Dropping audio chunk."
                    )

                continue

            # =================================================================
            # Text message
            # =================================================================

            text_message = message.get(
                "text"
            )

            if not text_message:

                continue

            try:

                payload = json.loads(
                    text_message
                )

            except json.JSONDecodeError:

                payload = {
                    "type": "text",
                    "text": text_message,
                }

            if not isinstance(
                payload,
                dict,
            ):

                continue

            message_type = payload.get(
                "type"
            )

            # =================================================================
            # Ping
            # =================================================================

            if message_type == "ping":

                await _send_json(
                    websocket,
                    {
                        "type": "pong",
                    },
                )

                continue

            # =================================================================
            # Language
            # =================================================================
            #
            # This message is acknowledged but does NOT override automatic
            # STT language detection.
            #
            # Voice requests continue to use:
            #
            #     result.language_code
            #
            # from Sarvam STT.
            # =================================================================

            if message_type == "language":

                requested_language = payload.get(
                    "language"
                )

                logger.info(
                    "Frontend language message: %s",
                    requested_language,
                )

                await _send_json(
                    websocket,
                    {
                        "type": "language",
                        "language": requested_language,
                    },
                )

                continue

            # =================================================================
            # Text request
            # =================================================================

            if message_type in {
                "text",
                None,
            }:

                user_text = payload.get(
                    "text"
                )

                if not isinstance(
                    user_text,
                    str,
                ):

                    continue

                user_text = (
                    user_text.strip()
                )

                if not user_text:

                    continue

                # -------------------------------------------------------------
                # Text requests currently do not have STT language metadata.
                #
                # Therefore language_code remains None and the TTS service
                # uses its configured/default language.
                # -------------------------------------------------------------

                await _process_agent_request(
                    websocket=websocket,
                    user_text=user_text,
                    account_email=account_email,
                    language_code=None,
                    generate_tts=False,
                )

                continue

            logger.warning(
                "Unknown WebSocket message type: %s",
                message_type,
            )

    except WebSocketDisconnect:

        logger.info(
            "Voice WebSocket disconnected."
        )

    except asyncio.CancelledError:

        raise

    except Exception:

        logger.exception(
            "Voice WebSocket failed."
        )

        await _send_json(
            websocket,
            {
                "type": "error",
                "message": (
                    "Voice processing failed."
                ),
            },
        )

    finally:

        # =====================================================================
        # Stop audio stream
        # =====================================================================

        try:

            audio_queue.put_nowait(
                None
            )

        except asyncio.QueueFull:

            pass

        # =====================================================================
        # Stop STT task
        # =====================================================================

        if not stt_task.done():

            stt_task.cancel()

        try:

            await stt_task

        except asyncio.CancelledError:

            pass

        except Exception:

            logger.debug(
                "STT cleanup failed.",
                exc_info=True,
            )

        logger.info(
            "VOICE WEBSOCKET SESSION COMPLETED"
        )

