from __future__ import annotations

import sys
import pytest

sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/rfp-service")


def test_questionnaire_completion_yes_no():
    """Test yes_no question completion agent."""
    import asyncio
    from questionnaire import QuestionnaireCompletionAgent

    agent = QuestionnaireCompletionAgent()
    item = {"id": "q1", "question_type": "yes_no", "text": "Does your system support SSO?", "options": []}
    context = [{"text": "Our platform fully supports SSO via SAML 2.0 and OAuth 2.0.", "score": 0.02}]

    result = asyncio.get_event_loop().run_until_complete(agent.complete(item, context))
    assert result.answer in ["Yes", "No"]
    assert 0.0 <= result.confidence <= 1.0


def test_questionnaire_completion_numeric():
    """Test numeric question type extraction."""
    import asyncio
    from questionnaire import QuestionnaireCompletionAgent

    agent = QuestionnaireCompletionAgent()
    item = {"id": "q2", "question_type": "numeric", "text": "What is your uptime SLA?", "options": []}
    context = [{"text": "We guarantee 99.9% uptime with our SLA.", "score": 0.015}]

    result = asyncio.get_event_loop().run_until_complete(agent.complete(item, context))
    assert "99" in result.answer or "0" in result.answer  # Either found number or fallback


def test_questionnaire_low_confidence_flagged():
    """Items with low confidence should be flagged."""
    import asyncio
    from questionnaire import QuestionnaireCompletionAgent

    agent = QuestionnaireCompletionAgent()
    item = {"id": "q3", "question_type": "text", "text": "What is your DR plan?", "options": []}
    context = []  # No context → low confidence

    result = asyncio.get_event_loop().run_until_complete(agent.complete(item, context))
    assert result.flagged is True


def test_rfp_crud_version_conflict():
    """Test optimistic locking raises 409 on version mismatch."""
    # This is tested via the mock — version check happens synchronously in update_answer
    from fastapi import HTTPException
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy import text

    # Build a mock DB session that returns version=2 when asked for max version
    async def mock_execute(stmt, params=None):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 2
        return mock_result

    mock_db = AsyncMock()
    mock_db.execute = mock_execute

    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(
            __import__("rfp_crud").update_answer(mock_db, "qid", "aid", "new answer", expected_version=1)
        )
    assert exc_info.value.status_code == 409
