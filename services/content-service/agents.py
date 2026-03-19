from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.logging import get_logger

logger = get_logger("content-service.agents")


@dataclass
class Requirement:
    text: str
    category: str
    scoring_criteria: dict
    is_questionnaire: bool = False


@dataclass
class QuestionnaireItem:
    question_text: str
    question_type: str  # yes_no, multiple_choice, numeric, text
    options: list[str] | None = None


class RequirementExtractionAgent:
    """LLM-based extraction of requirements from RFP text."""

    def extract(self, rfp_text: str) -> list[Requirement]:
        """
        Extract requirements from RFP text using heuristic + LLM pattern.
        For MVP: uses pattern matching; real impl calls LLM in Phase 4.
        """
        requirements = []
        lines = rfp_text.split("\n")
        current_category = "General"

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Detect category headers
            if line.isupper() and len(line) < 80:
                current_category = line.title()
                continue
            # Detect requirement-like lines
            if any(line.startswith(prefix) for prefix in ["The vendor shall", "The system shall", "Must ", "Should ", "Shall ", "Required:"]):
                requirements.append(Requirement(
                    text=line,
                    category=current_category,
                    scoring_criteria={"weight": 1.0},
                    is_questionnaire=False,
                ))

        return requirements

    async def extract_and_store(
        self, db: AsyncSession, rfp_id: str, rfp_text: str
    ) -> list[str]:
        """Extract requirements and insert into rfp_requirements."""
        requirements = self.extract(rfp_text)
        requirement_ids = []

        for req in requirements:
            req_id = str(uuid.uuid4())
            await db.execute(
                text(
                    "INSERT INTO rfp_requirements (id, rfp_id, text, category, scoring_criteria, is_questionnaire) "
                    "VALUES (:id, :rfp_id, :text, :category, :scoring::jsonb, :is_q)"
                ),
                {
                    "id": req_id,
                    "rfp_id": rfp_id,
                    "text": req.text,
                    "category": req.category,
                    "scoring": json.dumps(req.scoring_criteria),
                    "is_q": req.is_questionnaire,
                },
            )
            requirement_ids.append(req_id)

        await db.commit()
        logger.info(f"Extracted {len(requirements)} requirements for RFP {rfp_id}")
        return requirement_ids


class QuestionnaireExtractionAgent:
    """Detect and classify questionnaire items from RFP text."""

    _YES_NO_KEYWORDS = ["yes/no", "yes or no", "true/false", "confirm", "does your", "can your", "is your", "will your"]
    _NUMERIC_KEYWORDS = ["how many", "number of", "quantity", "percentage", "rate", "uptime", "sla"]

    def extract(self, rfp_text: str) -> list[QuestionnaireItem]:
        items = []
        lines = rfp_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line or not line.endswith("?"):
                continue

            lower = line.lower()
            if any(kw in lower for kw in self._YES_NO_KEYWORDS):
                question_type = "yes_no"
                options = None
            elif any(kw in lower for kw in self._NUMERIC_KEYWORDS):
                question_type = "numeric"
                options = None
            else:
                question_type = "text"
                options = None

            items.append(QuestionnaireItem(
                question_text=line,
                question_type=question_type,
                options=options,
            ))

        return items

    async def extract_and_store(
        self, db: AsyncSession, rfp_id: str, rfp_text: str
    ) -> list[str]:
        """Extract questionnaire items and insert into questionnaire_items via rfp_requirements."""
        items = self.extract(rfp_text)
        item_ids = []

        for item in items:
            # Create a parent rfp_requirement row first
            req_id = str(uuid.uuid4())
            await db.execute(
                text(
                    "INSERT INTO rfp_requirements (id, rfp_id, text, category, scoring_criteria, is_questionnaire) "
                    "VALUES (:id, :rfp_id, :text, :category, :scoring::jsonb, true)"
                ),
                {
                    "id": req_id,
                    "rfp_id": rfp_id,
                    "text": item.question_text,
                    "category": "Questionnaire",
                    "scoring": json.dumps({"weight": 1.0}),
                },
            )

            item_id = str(uuid.uuid4())
            await db.execute(
                text(
                    "INSERT INTO questionnaire_items (id, rfp_requirement_id, question_type, options, flagged) "
                    "VALUES (:id, :req_id, :qtype, :opts::jsonb, false)"
                ),
                {
                    "id": item_id,
                    "req_id": req_id,
                    "qtype": item.question_type,
                    "opts": json.dumps(item.options) if item.options else "null",
                },
            )
            item_ids.append(item_id)

        await db.commit()
        logger.info(f"Extracted {len(items)} questionnaire items for RFP {rfp_id}")
        return item_ids
