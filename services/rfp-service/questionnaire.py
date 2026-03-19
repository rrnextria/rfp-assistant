from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.logging import get_logger

logger = get_logger("rfp-service.questionnaire")

CONFIDENCE_THRESHOLD = 0.7


@dataclass
class CompletedItem:
    item_id: str
    answer: str
    confidence: float
    flagged: bool


class QuestionnaireCompletionAgent:
    """Complete questionnaire items with typed answers using retrieval context."""

    def _compute_confidence(self, chunks: list[dict], answer_type: str) -> float:
        """
        Model-agnostic confidence proxy:
        - For yes_no and multiple_choice: based on retrieval score strength
        - For text/numeric: mean chunk score normalized
        """
        if not chunks:
            return 0.0
        scores = [float(c.get("score", 0)) for c in chunks]
        mean_score = sum(scores) / len(scores)
        # Normalize: RRF max score ≈ 1/60
        normalized = min(mean_score / (1.0 / 60), 1.0)
        # For text/numeric, also factor in keyword overlap (simplified: 70% of normalized)
        return round(normalized * 0.7 + 0.3 * (1.0 if len(chunks) >= 3 else 0.0), 3)

    async def complete(
        self,
        item: dict,
        context_chunks: list[dict],
        db: AsyncSession | None = None,
    ) -> CompletedItem:
        question_type = item.get("question_type", "text")
        options = item.get("options") or []
        question_text = item.get("text", item.get("question_text", ""))

        context_text = "\n".join(c.get("text", "") for c in context_chunks[:5])

        # Generate answer based on type
        if question_type == "yes_no":
            # Simple heuristic: check if context contains affirmative keywords
            affirmatives = ["yes", "support", "provide", "offer", "comply", "certified", "available"]
            lower_ctx = context_text.lower()
            answer = "Yes" if any(a in lower_ctx for a in affirmatives) else "No"
        elif question_type == "multiple_choice" and options:
            # Pick first option that appears in context, else first option
            answer = options[0]
            lower_ctx = context_text.lower()
            for opt in options:
                if opt.lower() in lower_ctx:
                    answer = opt
                    break
        elif question_type == "numeric":
            # Extract first number from context
            import re
            numbers = re.findall(r"\b\d+(?:\.\d+)?%?\b", context_text)
            answer = numbers[0] if numbers else "0"
        else:
            # text type: use first sentence of context
            sentences = context_text.split(".")
            answer = sentences[0].strip() + "." if sentences else "See documentation."

        confidence = self._compute_confidence(context_chunks, question_type)
        flagged = confidence < CONFIDENCE_THRESHOLD

        return CompletedItem(
            item_id=item.get("id", ""),
            answer=answer,
            confidence=confidence,
            flagged=flagged,
        )

    async def complete_all_for_rfp(
        self, db: AsyncSession, rfp_id: str, user_context: dict
    ) -> dict:
        """Run completion for all unfilled questionnaire_items for an RFP."""
        # Get questionnaire items via rfp_requirements
        rows = await db.execute(
            text(
                "SELECT qi.id, qi.question_type, qi.options, qi.answer, "
                "rr.text as text "
                "FROM questionnaire_items qi "
                "JOIN rfp_requirements rr ON rr.id = qi.rfp_requirement_id "
                "WHERE rr.rfp_id = :rfp_id AND qi.answer IS NULL"
            ),
            {"rfp_id": rfp_id},
        )
        items = [dict(r) for r in rows.mappings().all()]

        completed_count = 0
        flagged_count = 0
        results = []

        for item in items:
            # Get context via retrieval service
            sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/orchestrator")
            from pipeline import call_retrieval_service
            chunks = await call_retrieval_service(
                question=item["text"],
                user_context=user_context,
            )

            result = await self.complete(item, chunks, db)

            # Update database
            await db.execute(
                text(
                    "UPDATE questionnaire_items SET answer = :answer, confidence = :confidence, flagged = :flagged "
                    "WHERE id = :id"
                ),
                {
                    "answer": result.answer,
                    "confidence": result.confidence,
                    "flagged": result.flagged,
                    "id": item["id"],
                },
            )
            completed_count += 1
            if result.flagged:
                flagged_count += 1
            results.append({
                "item_id": item["id"],
                "answer": result.answer,
                "confidence": result.confidence,
                "flagged": result.flagged,
            })

        await db.commit()
        return {"completed": completed_count, "flagged": flagged_count, "results": results}
