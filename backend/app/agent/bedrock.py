from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
)

from app.config.settings import get_settings


class BedrockService:
    """
    Central Amazon Bedrock service.

    Responsibilities:

    - Use configured provider/model/region.
    - Invoke Bedrock Converse.
    - Keep prompts within a safe input budget.
    - Keep generation settings configurable.
    - Retry automatically with a smaller context if
      Bedrock reports that the input is too large.
    - Parse model responses safely.
    - Robustly extract JSON when the model adds harmless
      prefixes such as "JSON:" or markdown fences.

    Important:

    This service does NOT use the Bedrock CountTokens API.

    Some configured Bedrock models do not support CountTokens.
    Therefore prompt-size management is handled locally.
    """

    # =========================================================
    # Safe Input Budget
    # =========================================================

    SAFE_INPUT_CHAR_LIMIT = 500_000

    RETRY_INPUT_CHAR_LIMIT = 250_000

    FINAL_INPUT_CHAR_LIMIT = 120_000

    NORMAL_TEXT_BLOCK_LIMIT = 40_000

    RETRY_TEXT_BLOCK_LIMIT = 20_000

    FINAL_TEXT_BLOCK_LIMIT = 10_000

    # =========================================================
    # Initialization
    # =========================================================

    def __init__(self) -> None:

        self.settings = get_settings()

        self.client = boto3.client(
            "bedrock-runtime",
            region_name=self.settings.aws_region,
        )

    # =========================================================
    # Configuration
    # =========================================================

    @property
    def provider(self) -> str:

        return (
            self.settings.llm_provider
            or ""
        ).strip()

    @property
    def model_id(self) -> str:

        model_id = (
            self.settings.llm_model
            or ""
        ).strip()

        if not model_id:

            raise RuntimeError(
                "LLM model is not configured."
            )

        return model_id

    @property
    def region(self) -> str:

        region = (
            self.settings.aws_region
            or ""
        ).strip()

        if not region:

            raise RuntimeError(
                "AWS region is not configured."
            )

        return region

    # =========================================================
    # Text Compaction
    # =========================================================

    @staticmethod
    def _compact_text(
        text: str,
        max_chars: int,
    ) -> str:
        """
        Reduce one text block while preserving both the
        beginning and the end.

        No Gmail-specific values or intent mappings are
        hardcoded here.
        """

        if not isinstance(
            text,
            str,
        ):
            return ""

        if len(text) <= max_chars:

            return text

        if max_chars <= 100:

            return text[:max_chars]

        marker = (
            "\n\n"
            "[content compacted]"
            "\n\n"
        )

        available = (
            max_chars
            - len(marker)
        )

        if available <= 0:

            return text[:max_chars]

        first_half = (
            available // 2
        )

        second_half = (
            available
            - first_half
        )

        return (
            text[:first_half]
            + marker
            + text[-second_half:]
        )

    # =========================================================
    # Message Text Size
    # =========================================================

    @staticmethod
    def _message_text_length(
        message: dict[str, Any],
    ) -> int:
        """
        Calculate approximate character count contained
        in one Bedrock message.
        """

        content = message.get(
            "content",
            [],
        )

        if not isinstance(
            content,
            list,
        ):

            return 0

        total = 0

        for item in content:

            if not isinstance(
                item,
                dict,
            ):
                continue

            text = item.get(
                "text"
            )

            if isinstance(
                text,
                str,
            ):

                total += len(text)

        return total

    # =========================================================
    # Total Input Size
    # =========================================================

    def _calculate_input_size(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None,
    ) -> int:
        """
        Calculate approximate input size using characters.

        This is intentionally not presented as an exact
        token count.
        """

        total = 0

        if system_prompt:

            total += len(
                system_prompt
            )

        for message in messages:

            if isinstance(
                message,
                dict,
            ):

                total += (
                    self._message_text_length(
                        message
                    )
                )

        return total

    # =========================================================
    # Compact Individual Message
    # =========================================================

    def _compact_message(
        self,
        message: dict[str, Any],
        text_limit: int,
    ) -> dict[str, Any]:
        """
        Return a compacted copy of one Bedrock message.
        """

        copied = dict(
            message
        )

        content = copied.get(
            "content"
        )

        if not isinstance(
            content,
            list,
        ):

            return copied

        new_content: list[
            dict[str, Any]
        ] = []

        for item in content:

            if not isinstance(
                item,
                dict,
            ):
                continue

            new_item = dict(
                item
            )

            text = new_item.get(
                "text"
            )

            if isinstance(
                text,
                str,
            ):

                new_item["text"] = (
                    self._compact_text(
                        text,
                        text_limit,
                    )
                )

            new_content.append(
                new_item
            )

        copied["content"] = (
            new_content
        )

        return copied

    # =========================================================
    # Compact Complete Prompt
    # =========================================================

    def _compact_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None,
        text_limit: int,
        total_limit: int,
    ) -> tuple[
        list[dict[str, Any]],
        str | None,
    ]:
        """
        Compact the complete request.

        Recent messages are preserved before older messages.

        The newest user message is always retained whenever
        possible.
        """

        valid_messages: list[
            dict[str, Any]
        ] = []

        for message in messages:

            if not isinstance(
                message,
                dict,
            ):
                continue

            valid_messages.append(
                dict(message)
            )

        # -----------------------------------------------------
        # System prompt
        # -----------------------------------------------------

        compacted_system = (
            system_prompt
            if isinstance(
                system_prompt,
                str,
            )
            else None
        )

        if compacted_system:

            compacted_system = (
                self._compact_text(
                    compacted_system,
                    min(
                        text_limit,
                        30_000,
                    ),
                )
            )

        current_size = (
            len(
                compacted_system
            )
            if compacted_system
            else 0
        )

        # -----------------------------------------------------
        # Process newest → oldest
        # -----------------------------------------------------

        reversed_messages = list(
            reversed(
                valid_messages
            )
        )

        selected_reversed: list[
            dict[str, Any]
        ] = []

        for message in reversed_messages:

            compacted_message = (
                self._compact_message(
                    message,
                    text_limit,
                )
            )

            message_size = (
                self._message_text_length(
                    compacted_message
                )
            )

            estimated_size = (
                message_size + 100
            )

            if (
                selected_reversed
                and
                current_size
                + estimated_size
                > total_limit
            ):

                continue

            selected_reversed.append(
                compacted_message
            )

            current_size += (
                estimated_size
            )

            if current_size >= total_limit:

                break

        compacted_messages = list(
            reversed(
                selected_reversed
            )
        )

        # -----------------------------------------------------
        # Always retain newest message
        # -----------------------------------------------------

        if valid_messages:

            newest = (
                valid_messages[-1]
            )

            newest_compacted = (
                self._compact_message(
                    newest,
                    text_limit,
                )
            )

            if not compacted_messages:

                compacted_messages = [
                    newest_compacted
                ]

            else:

                newest_text = json.dumps(
                    newest_compacted,
                    ensure_ascii=False,
                )

                already_present = any(
                    json.dumps(
                        item,
                        ensure_ascii=False,
                    )
                    == newest_text
                    for item
                    in compacted_messages
                )

                if not already_present:

                    compacted_messages.append(
                        newest_compacted
                    )

        return (
            compacted_messages,
            compacted_system,
        )

    # =========================================================
    # Build Converse Request
    # =========================================================

    def _build_converse_kwargs(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None,
        inference_config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build Amazon Bedrock Converse request.
        """

        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": messages,
            "inferenceConfig": inference_config,
        }

        if (
            system_prompt
            and system_prompt.strip()
        ):

            kwargs["system"] = [
                {
                    "text": (
                        system_prompt.strip()
                    )
                }
            ]

        return kwargs

    # =========================================================
    # Context Error Detection
    # =========================================================

    @staticmethod
    def _is_context_error(
        exc: Exception,
    ) -> bool:
        """
        Determine whether Bedrock rejected the request because
        the input/context is too large.
        """

        error_text = str(
            exc
        ).lower()

        indicators = (
            "input tokens exceeded",
            "maximum length",
            "context length",
            "context window",
            "too many tokens",
            "input is too large",
            "prompt is too large",
            "request is too large",
        )

        return any(
            indicator in error_text
            for indicator in indicators
        )

    # =========================================================
    # Bedrock Error Logging
    # =========================================================

    def _log_failure(
        self,
        exc: Exception,
    ) -> None:

        print("=" * 70)

        print(
            "BEDROCK INVOCATION FAILED"
        )

        print(
            "Provider:",
            self.provider,
        )

        print(
            "Model:",
            self.model_id,
        )

        print(
            "Region:",
            self.region,
        )

        print(
            "Exception type:",
            type(exc).__name__,
        )

        print(
            "Exception:",
            str(exc),
        )

        print("=" * 70)

    # =========================================================
    # Invoke
    # =========================================================

    def invoke(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str:
        """
        Invoke the configured Bedrock model.

        Uses local character-based context protection rather
        than the CountTokens API.
        """

        if not messages:

            raise ValueError(
                "At least one message is required."
            )

        # -----------------------------------------------------
        # Resolve generation settings
        # -----------------------------------------------------

        resolved_max_tokens = (
            max_tokens
            if max_tokens is not None
            else self.settings.llm_max_tokens
        )

        resolved_temperature = (
            temperature
            if temperature is not None
            else self.settings.llm_temperature
        )

        resolved_top_p = (
            top_p
            if top_p is not None
            else self.settings.llm_top_p
        )

        # -----------------------------------------------------
        # Validate max tokens
        # -----------------------------------------------------

        if resolved_max_tokens <= 0:

            raise ValueError(
                "LLM max tokens must be greater than zero."
            )

        # Nova Pro supports up to 5,000 generated tokens.

        resolved_max_tokens = min(
            int(
                resolved_max_tokens
            ),
            5000,
        )

        # -----------------------------------------------------
        # Validate temperature
        # -----------------------------------------------------

        if not 0.0 <= resolved_temperature <= 1.0:

            raise ValueError(
                "LLM temperature must be between 0 and 1."
            )

        # -----------------------------------------------------
        # Validate top_p
        # -----------------------------------------------------

        if (
            resolved_top_p is not None
            and not 0.0 < resolved_top_p <= 1.0
        ):

            raise ValueError(
                "LLM top_p must be greater than 0 and at most 1."
            )

        # -----------------------------------------------------
        # Build inference configuration
        # -----------------------------------------------------

        inference_config: dict[
            str,
            Any,
        ] = {
            "maxTokens": (
                resolved_max_tokens
            ),
            "temperature": (
                resolved_temperature
            ),
        }

        # Only send topP when it is configured.

        if resolved_top_p is not None:

            inference_config["topP"] = (
                resolved_top_p
            )

        # =====================================================
        # Stage 1
        # =====================================================

        original_size = (
            self._calculate_input_size(
                messages=messages,
                system_prompt=system_prompt,
            )
        )

        print(
            "BEDROCK INPUT SIZE:",
            original_size,
            "characters",
        )

        if (
            original_size
            <= self.SAFE_INPUT_CHAR_LIMIT
        ):

            converse_kwargs = (
                self._build_converse_kwargs(
                    messages=messages,
                    system_prompt=system_prompt,
                    inference_config=(
                        inference_config
                    ),
                )
            )

        else:

            print(
                "BEDROCK INPUT LARGE - "
                "COMPACTING BEFORE INVOCATION"
            )

            (
                compacted_messages,
                compacted_system,
            ) = self._compact_messages(
                messages=messages,
                system_prompt=system_prompt,
                text_limit=(
                    self.NORMAL_TEXT_BLOCK_LIMIT
                ),
                total_limit=(
                    self.RETRY_INPUT_CHAR_LIMIT
                ),
            )

            converse_kwargs = (
                self._build_converse_kwargs(
                    messages=compacted_messages,
                    system_prompt=compacted_system,
                    inference_config=(
                        inference_config
                    ),
                )
            )

        # =====================================================
        # Stage 2 - First Bedrock call
        # =====================================================

        try:

            response = (
                self.client.converse(
                    **converse_kwargs
                )
            )

        except (
            ClientError,
            BotoCoreError,
        ) as exc:

            if not self._is_context_error(
                exc
            ):

                self._log_failure(
                    exc
                )

                raise RuntimeError(
                    "Unable to invoke Amazon Bedrock model."
                ) from exc

            # -------------------------------------------------
            # Context too large.
            # Retry with compacted prompt.
            # -------------------------------------------------

            print(
                "BEDROCK INPUT TOO LARGE - "
                "RETRYING WITH COMPACTED PROMPT"
            )

            (
                compacted_messages,
                compacted_system,
            ) = self._compact_messages(
                messages=messages,
                system_prompt=system_prompt,
                text_limit=(
                    self.RETRY_TEXT_BLOCK_LIMIT
                ),
                total_limit=(
                    self.FINAL_INPUT_CHAR_LIMIT
                ),
            )

            compacted_kwargs = (
                self._build_converse_kwargs(
                    messages=compacted_messages,
                    system_prompt=compacted_system,
                    inference_config=(
                        inference_config
                    ),
                )
            )

            compacted_size = (
                self._calculate_input_size(
                    messages=compacted_messages,
                    system_prompt=compacted_system,
                )
            )

            print(
                "BEDROCK COMPACTED INPUT SIZE:",
                compacted_size,
                "characters",
            )

            try:

                response = (
                    self.client.converse(
                        **compacted_kwargs
                    )
                )

            except (
                ClientError,
                BotoCoreError,
            ):

                # -------------------------------------------------
                # Final retry.
                # -------------------------------------------------

                print(
                    "BEDROCK SECOND CONTEXT RETRY FAILED - "
                    "USING FINAL COMPACT PROMPT"
                )

                (
                    final_messages,
                    final_system,
                ) = self._compact_messages(
                    messages=messages,
                    system_prompt=system_prompt,
                    text_limit=(
                        self.FINAL_TEXT_BLOCK_LIMIT
                    ),
                    total_limit=(
                        60_000
                    ),
                )

                final_kwargs = (
                    self._build_converse_kwargs(
                        messages=final_messages,
                        system_prompt=final_system,
                        inference_config=(
                            inference_config
                        ),
                    )
                )

                try:

                    response = (
                        self.client.converse(
                            **final_kwargs
                        )
                    )

                except (
                    ClientError,
                    BotoCoreError,
                ) as final_exc:

                    self._log_failure(
                        final_exc
                    )

                    raise RuntimeError(
                        "Unable to invoke Amazon Bedrock model "
                        "because the input is too large."
                    ) from final_exc

        # =====================================================
        # Extract Bedrock response
        # =====================================================

        output = response.get(
            "output",
            {},
        )

        if not isinstance(
            output,
            dict,
        ):

            raise RuntimeError(
                "Amazon Bedrock returned an invalid output."
            )

        message = output.get(
            "message",
            {},
        )

        if not isinstance(
            message,
            dict,
        ):

            raise RuntimeError(
                "Amazon Bedrock returned an invalid message."
            )

        content = message.get(
            "content",
            [],
        )

        if not isinstance(
            content,
            list,
        ):

            raise RuntimeError(
                "Amazon Bedrock returned invalid content."
            )

        parts: list[str] = []

        for item in content:

            if not isinstance(
                item,
                dict,
            ):

                continue

            text = item.get(
                "text"
            )

            if (
                isinstance(
                    text,
                    str,
                )
                and text.strip()
            ):

                parts.append(
                    text.strip()
                )

        result = "\n".join(
            parts
        ).strip()

        if not result:

            raise RuntimeError(
                "Amazon Bedrock returned an empty response."
            )

        return result

    # =========================================================
    # JSON Cleaning
    # =========================================================

    @staticmethod
    def _clean_json_response(
        response_text: str,
    ) -> str:
        """
        Clean common formatting added by an LLM before JSON.

        Handles examples such as:

            {
              "decision": "confirm"
            }

        and:

            JSON:
            {
              "decision": "confirm"
            }

        and:

            ```json
            {
              "decision": "confirm"
            }
            ```

        It does not introduce any hardcoded Gmail values,
        recipients, message IDs, thread IDs, subjects, etc.
        """

        if not isinstance(
            response_text,
            str,
        ):

            raise RuntimeError(
                "Amazon Bedrock returned a non-text JSON response."
            )

        cleaned = response_text.strip()

        if not cleaned:

            raise RuntimeError(
                "Amazon Bedrock returned an empty JSON response."
            )

        # -----------------------------------------------------
        # Remove markdown code fences
        # -----------------------------------------------------

        if cleaned.startswith(
            "```"
        ):

            lines = (
                cleaned.splitlines()
            )

            # Remove first fence line.
            if lines:

                lines = lines[1:]

            # Remove closing fence.
            if (
                lines
                and lines[-1].strip()
                == "```"
            ):

                lines = lines[:-1]

            cleaned = "\n".join(
                lines
            ).strip()

        # -----------------------------------------------------
        # Remove common "JSON:" prefix
        # -----------------------------------------------------

        if cleaned.lower().startswith(
            "json:"
        ):

            cleaned = (
                cleaned[5:]
                .strip()
            )

        # -----------------------------------------------------
        # Remove optional language/presentation prefixes
        # -----------------------------------------------------

        prefixes = (
            "json\n",
            "json\r\n",
            "JSON\n",
            "JSON\r\n",
        )

        for prefix in prefixes:

            if cleaned.startswith(
                prefix
            ):

                cleaned = (
                    cleaned[len(prefix):]
                    .strip()
                )

        return cleaned

    # =========================================================
    # Extract JSON Object
    # =========================================================

    @staticmethod
    def _extract_json_object(
        response_text: str,
    ) -> dict[str, Any]:
        """
        Extract a JSON object from an LLM response.

        This is more robust than directly calling json.loads()
        because the model may return:

            JSON:
            {...}

        or:

            Here is the JSON:
            {...}

        or markdown fenced JSON.

        The JSON decoder is still used to validate the actual
        JSON structure.
        """

        cleaned = (
            BedrockService._clean_json_response(
                response_text
            )
        )

        # -----------------------------------------------------
        # First attempt:
        # Entire response is JSON.
        # -----------------------------------------------------

        try:

            parsed = json.loads(
                cleaned
            )

            if isinstance(
                parsed,
                dict,
            ):

                return parsed

        except json.JSONDecodeError:

            pass

        # -----------------------------------------------------
        # Second attempt:
        #
        # Find a JSON object embedded inside surrounding text.
        # -----------------------------------------------------

        decoder = json.JSONDecoder()

        for index, character in enumerate(
            cleaned
        ):

            if character != "{":

                continue

            candidate = (
                cleaned[index:]
            )

            try:

                parsed, _ = (
                    decoder.raw_decode(
                        candidate
                    )
                )

            except json.JSONDecodeError:

                continue

            if isinstance(
                parsed,
                dict,
            ):

                return parsed

        # -----------------------------------------------------
        # Nothing valid found.
        # -----------------------------------------------------

        print("=" * 70)

        print(
            "BEDROCK JSON PARSING FAILED"
        )

        print(
            "RAW RESPONSE:"
        )

        print(
            response_text
        )

        print(
            "CLEANED RESPONSE:"
        )

        print(
            cleaned
        )

        print("=" * 70)

        raise RuntimeError(
            "Amazon Bedrock returned invalid JSON."
        )

    # =========================================================
    # JSON Response
    # =========================================================

    def invoke_json(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> dict[str, Any]:
        """
        Invoke Bedrock and parse the result as JSON.

        The parser accepts valid JSON even if the model wraps
        it with harmless formatting such as:

            JSON:
            {...}

        or markdown fences.
        """

        response_text = self.invoke(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=(
                temperature
                if temperature is not None
                else 0.0
            ),
            top_p=(
                top_p
                if top_p is not None
                else None
            ),
        )

        parsed = (
            self._extract_json_object(
                response_text
            )
        )

        if not isinstance(
            parsed,
            dict,
        ):

            raise RuntimeError(
                "Amazon Bedrock JSON response must be an object."
            )

        return parsed


# =============================================================
# Shared service instance
# =============================================================

bedrock_service = BedrockService()