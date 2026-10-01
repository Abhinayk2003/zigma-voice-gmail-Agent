from __future__ import annotations

import logging
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config.settings import get_settings


logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """
    Amazon Bedrock Knowledge Base retrieval service.

    Responsibilities:
        - Connect to Amazon Bedrock Agent Runtime.
        - Retrieve relevant chunks from the configured Knowledge Base.
        - Return retrieved source information.

    This service DOES NOT generate the final answer.

    Final answer generation remains in the existing BedrockService
    used by the Gmail orchestrator.

    Configuration priority:

        Knowledge Base ID:
            1. BEDROCK_KNOWLEDGE_BASE_ID environment variable
            2. settings.bedrock_kb_id

        AWS region:
            1. settings.aws_region
            2. LLM_REGION
            3. AWS_REGION
            4. us-east-1

    Optional environment variables:

        BEDROCK_KNOWLEDGE_BASE_TOP_K=5
        BEDROCK_KNOWLEDGE_BASE_SCORE_THRESHOLD=0
    """

    def __init__(self) -> None:

        settings = get_settings()

        # =========================================================
        # AWS REGION
        # =========================================================

        configured_region = (
            getattr(
                settings,
                "aws_region",
                None,
            )
            or os.getenv("LLM_REGION")
            or os.getenv("AWS_REGION")
            or "us-east-1"
        )

        self.region = str(
            configured_region
        ).strip()

        # =========================================================
        # KNOWLEDGE BASE ID
        # =========================================================
        #
        # Prefer environment variable.
        #
        # If it is not present, use the existing application
        # setting:
        #
        #     settings.bedrock_kb_id
        #
        # This prevents the KB service from becoming disabled
        # simply because BEDROCK_KNOWLEDGE_BASE_ID was not added
        # separately to .env.
        # =========================================================

        environment_kb_id = (
            os.getenv(
                "BEDROCK_KNOWLEDGE_BASE_ID"
            )
            or ""
        ).strip()

        settings_kb_id = (
            getattr(
                settings,
                "bedrock_kb_id",
                None,
            )
            or ""
        )

        self.knowledge_base_id = (
            environment_kb_id
            or str(settings_kb_id).strip()
        )

        # =========================================================
        # RETRIEVAL SETTINGS
        # =========================================================

        self.top_k = self._positive_int_env(
            name="BEDROCK_KNOWLEDGE_BASE_TOP_K",
            default=5,
            maximum=20,
        )

        self.score_threshold = self._float_env(
            name="BEDROCK_KNOWLEDGE_BASE_SCORE_THRESHOLD",
            default=0.0,
        )

        # =========================================================
        # BEDROCK AGENT RUNTIME CLIENT
        # =========================================================

        self.client = boto3.client(
            "bedrock-agent-runtime",
            region_name=self.region,
        )

        logger.info(
            "Knowledge Base service initialized: "
            "region=%s kb_id=%s top_k=%s score_threshold=%s",
            self.region,
            self.knowledge_base_id or "NOT_CONFIGURED",
            self.top_k,
            self.score_threshold,
        )

    # =============================================================
    # ENVIRONMENT HELPERS
    # =============================================================

    @staticmethod
    def _positive_int_env(
        name: str,
        default: int,
        maximum: int,
    ) -> int:

        try:

            value = int(
                os.getenv(
                    name,
                    str(default),
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            value = default

        return max(
            1,
            min(
                value,
                maximum,
            ),
        )

    @staticmethod
    def _float_env(
        name: str,
        default: float,
    ) -> float:

        try:

            return max(
                0.0,
                float(
                    os.getenv(
                        name,
                        str(default),
                    )
                ),
            )

        except (
            TypeError,
            ValueError,
        ):

            return default

    # =============================================================
    # ENABLED
    # =============================================================

    @property
    def enabled(self) -> bool:

        return bool(
            self.knowledge_base_id
        )

    # =============================================================
    # RETRIEVE
    # =============================================================

    def retrieve(
        self,
        query: str,
    ) -> dict[str, Any]:
        """
        Retrieve relevant chunks from Amazon Bedrock Knowledge Base.

        No final answer is generated here.

        Returns a structure containing:
            - query
            - knowledge_base_id
            - result_count
            - retrieved chunks
        """

        # ---------------------------------------------------------
        # Validate query
        # ---------------------------------------------------------

        cleaned_query = (
            query or ""
        ).strip()

        if not cleaned_query:

            raise ValueError(
                "Knowledge Base query cannot be empty."
            )

        # ---------------------------------------------------------
        # Validate KB configuration
        # ---------------------------------------------------------

        if not self.knowledge_base_id:

            raise RuntimeError(
                "Knowledge Base is not configured. "
                "Set BEDROCK_KNOWLEDGE_BASE_ID or "
                "configure bedrock_kb_id in settings."
            )

        # ---------------------------------------------------------
        # Defensive query limit
        # ---------------------------------------------------------

        cleaned_query = (
            cleaned_query[:20_000]
        )

        logger.info(
            "============================================================"
        )

        logger.info(
            "KNOWLEDGE BASE RETRIEVAL"
        )

        logger.info(
            "AWS REGION: %s",
            self.region,
        )

        logger.info(
            "KNOWLEDGE BASE ID: %s",
            self.knowledge_base_id,
        )

        logger.info(
            "QUERY: %s",
            cleaned_query,
        )

        logger.info(
            "TOP K: %s",
            self.top_k,
        )

        logger.info(
            "SCORE THRESHOLD: %s",
            self.score_threshold,
        )

        logger.info(
            "============================================================"
        )

        # =========================================================
        # CALL BEDROCK KNOWLEDGE BASE
        # =========================================================

        try:

            response = self.client.retrieve(
                knowledgeBaseId=(
                    self.knowledge_base_id
                ),
                retrievalConfiguration={
                    "vectorSearchConfiguration": {
                        "numberOfResults": self.top_k,
                    }
                },
                retrievalQuery={
                    "text": cleaned_query,
                },
            )

        except ClientError as exc:

            error_response = (
                getattr(
                    exc,
                    "response",
                    {},
                )
                or {}
            )

            error_data = (
                error_response.get(
                    "Error",
                    {},
                )
                or {}
            )

            error_code = (
                error_data.get(
                    "Code",
                    "Unknown",
                )
            )

            error_message = (
                error_data.get(
                    "Message",
                    str(exc),
                )
            )

            logger.exception(
                "Bedrock Knowledge Base ClientError: "
                "code=%s message=%s",
                error_code,
                error_message,
            )

            raise RuntimeError(
                "Knowledge Base retrieval failed: "
                f"{error_code}: {error_message}"
            ) from exc

        except BotoCoreError as exc:

            logger.exception(
                "Bedrock Knowledge Base boto error."
            )

            raise RuntimeError(
                "Knowledge Base retrieval failed: "
                f"{exc}"
            ) from exc

        except Exception as exc:

            logger.exception(
                "Unexpected Knowledge Base retrieval error."
            )

            raise RuntimeError(
                "Knowledge Base retrieval failed: "
                f"{exc}"
            ) from exc

        # =========================================================
        # PROCESS RETRIEVED RESULTS
        # =========================================================

        raw_results = (
            response.get(
                "retrievalResults",
                [],
            )
            or []
        )

        logger.info(
            "RAW KNOWLEDGE BASE RESULTS: %d",
            len(raw_results),
        )

        results: list[dict[str, Any]] = []

        for index, item in enumerate(
            raw_results,
            start=1,
        ):

            if not isinstance(
                item,
                dict,
            ):

                continue

            score = item.get(
                "score"
            )

            # -----------------------------------------------------
            # Score filtering
            # -----------------------------------------------------

            if (
                self.score_threshold > 0
                and isinstance(
                    score,
                    (int, float),
                )
                and score < self.score_threshold
            ):

                logger.debug(
                    "Skipping KB result %d "
                    "because score=%s < threshold=%s",
                    index,
                    score,
                    self.score_threshold,
                )

                continue

            # -----------------------------------------------------
            # Content
            # -----------------------------------------------------

            content = (
                item.get(
                    "content"
                )
                or {}
            )

            if isinstance(
                content,
                dict,
            ):

                text = content.get(
                    "text"
                )

            else:

                text = None

            text = (
                str(text).strip()
                if text
                else ""
            )

            if not text:

                logger.debug(
                    "Skipping KB result %d because content is empty.",
                    index,
                )

                continue

            # -----------------------------------------------------
            # Source location
            # -----------------------------------------------------

            location = (
                item.get(
                    "location"
                )
                or {}
            )

            source = (
                self._source_label(
                    location
                )
            )

            result_item = {
                "text": text,
                "score": score,
                "source": source,
                "location": location,
                "metadata": (
                    item.get(
                        "metadata"
                    )
                    or {}
                ),
            }

            results.append(
                result_item
            )

            logger.info(
                "KB RESULT %d: score=%s source=%s",
                index,
                score,
                source,
            )

        # =========================================================
        # FINAL RESULT
        # =========================================================

        result = {
            "success": True,
            "query": cleaned_query,
            "knowledge_base_id": (
                self.knowledge_base_id
            ),
            "results": results,
            "result_count": len(results),
        }

        logger.info(
            "Knowledge Base retrieval completed: "
            "results=%d",
            len(results),
        )

        return result

    # =============================================================
    # SOURCE LABEL
    # =============================================================

    @staticmethod
    def _source_label(
        location: dict[str, Any],
    ) -> str | None:

        if not isinstance(
            location,
            dict,
        ):

            return None

        # Common Bedrock Knowledge Base
        # location structures.

        for key in (
            "s3Location",
            "webLocation",
            "confluenceLocation",
            "sharePointLocation",
        ):

            value = location.get(
                key
            )

            if not isinstance(
                value,
                dict,
            ):

                continue

            for field in (
                "uri",
                "url",
            ):

                if value.get(field):

                    return str(
                        value[field]
                    )

        return None


# ============================================================================
# SINGLE SHARED INSTANCE
# ============================================================================

knowledge_base_service = KnowledgeBaseService()