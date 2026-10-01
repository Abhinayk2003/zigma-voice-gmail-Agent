from __future__ import annotations

import os
from typing import Any

import boto3


class KnowledgeBaseService:

    def __init__(self) -> None:

        self.region = os.getenv(
            "AWS_REGION",
            "ap-south-1",
        )

        self.knowledge_base_id = os.getenv(
            "BEDROCK_KNOWLEDGE_BASE_ID"
        )

        self.number_of_results = int(
            os.getenv(
                "KB_NUMBER_OF_RESULTS",
                "5",
            )
        )

        if not self.knowledge_base_id:
            raise ValueError(
                "BEDROCK_KNOWLEDGE_BASE_ID is not configured."
            )

        self.client = boto3.client(
            "bedrock-agent-runtime",
            region_name=self.region,
        )

    # ========================================================
    # RETRIEVE
    # ========================================================

    def retrieve(
        self,
        query: str,
    ) -> dict[str, Any]:

        if not query or not query.strip():
            raise ValueError(
                "Knowledge Base query is required."
            )

        response = self.client.retrieve(
            knowledgeBaseId=self.knowledge_base_id,
            retrievalQuery={
                "text": query.strip(),
            },
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": self.number_of_results,
                }
            },
        )

        results = []

        for item in response.get(
            "retrievalResults",
            [],
        ):

            content = (
                item.get("content", {})
                or {}
            )

            location = (
                item.get("location", {})
                or {}
            )

            metadata = (
                item.get("metadata", {})
                or {}
            )

            results.append(
                {
                    "text": content.get(
                        "text",
                        "",
                    ),
                    "score": item.get(
                        "score"
                    ),
                    "source": location,
                    "metadata": metadata,
                }
            )

        return {
            "query": query,
            "result_count": len(results),
            "results": results,
        }


knowledge_base_service = KnowledgeBaseService()