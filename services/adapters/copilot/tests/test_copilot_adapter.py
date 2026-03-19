"""Integration tests for the copilot channel adapter.

These tests mock:
- The Bot Framework adapter (skipping real JWT signature validation)
- The orchestrator HTTP call
- The database UPN resolution

They verify the full activity cycle:  message in → answer adaptive card out.

Run with:
    pytest services/adapters/copilot/tests/ -v
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Unit tests: adaptive_card
# ---------------------------------------------------------------------------

from services.adapters.copilot.adaptive_card import build_adaptive_card, build_error_card


def test_build_adaptive_card_structure():
    card = build_adaptive_card(
        answer="The compliance requirement is section 5.2.",
        citations=[
            {"chunk_id": "c1", "doc_id": "doc-001", "snippet": "Section 5.2 states..."}
        ],
        mode="answer",
    )
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5"
    texts = [b.get("text", "") for b in card["body"]]
    assert any("RFP Assistant" in t for t in texts)
    assert any("ANSWER" in t for t in texts)
    fact_sets = [b for b in card["body"] if b.get("type") == "FactSet"]
    assert len(fact_sets) == 1
    assert fact_sets[0]["facts"][0]["title"] == "doc-001"


def test_build_adaptive_card_no_citations():
    card = build_adaptive_card(answer="No sources needed.", citations=[], mode="draft")
    fact_sets = [b for b in card["body"] if b.get("type") == "FactSet"]
    assert len(fact_sets) == 0


def test_build_error_card():
    card = build_error_card("Not Registered", "Your account is not registered.")
    assert card["type"] == "AdaptiveCard"
    texts = [b.get("text", "") for b in card["body"]]
    assert any("Not Registered" in t for t in texts)


# ---------------------------------------------------------------------------
# Unit tests: auth helpers
# ---------------------------------------------------------------------------

from services.adapters.copilot.auth import build_user_context_header, get_service_jwt


def test_get_service_jwt_returns_string():
    token = get_service_jwt()
    assert isinstance(token, str)
    assert len(token) > 20


def test_get_service_jwt_cached():
    t1 = get_service_jwt()
    t2 = get_service_jwt()
    assert t1 == t2


def test_build_user_context_header():
    headers = build_user_context_header("user-123")
    assert headers == {"X-User-Id": "user-123"}


# ---------------------------------------------------------------------------
# Async tests: resolve_user
# ---------------------------------------------------------------------------

import pytest_asyncio  # noqa: E402 (imported for asyncio_mode)

from services.adapters.copilot.auth import resolve_user


@pytest.mark.asyncio
async def test_resolve_user_found():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.first.return_value = ("user-abc",)
    mock_db.execute.return_value = mock_result

    uid = await resolve_user("alice@example.com", mock_db)
    assert uid == "user-abc"


@pytest.mark.asyncio
async def test_resolve_user_not_found():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db.execute.return_value = mock_result

    uid = await resolve_user("ghost@example.com", mock_db)
    assert uid is None


# ---------------------------------------------------------------------------
# Async tests: TeamsBot handler (full turn simulation)
# ---------------------------------------------------------------------------

from botbuilder.schema import Activity, ActivityTypes, ChannelAccount

from services.adapters.copilot.handler import TeamsBot


def _make_activity(text: str, upn: str = "alice@example.com") -> Activity:
    activity = Activity(
        type=ActivityTypes.message,
        text=text,
        from_property=ChannelAccount(id="user-1", name=upn),
    )
    return activity


@pytest.mark.asyncio
async def test_bot_sends_answer_card(monkeypatch):
    """Full happy path: registered user gets an answer card."""
    # Patch resolve_user to return a user_id
    monkeypatch.setattr(
        "services.adapters.copilot.handler.resolve_user",
        AsyncMock(return_value="user-abc"),
    )

    # Patch httpx call to return a mock orchestrator response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "answer": "The answer is yes.",
        "citations": [{"chunk_id": "c1", "doc_id": "doc-001", "snippet": "Yes, section 3."}],
        "confidence": 0.9,
        "mode": "answer",
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    monkeypatch.setattr("services.adapters.copilot.handler.httpx.AsyncClient", lambda **kw: mock_client)

    # Mock db session factory
    mock_db = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db_factory = MagicMock(return_value=mock_db)

    bot = TeamsBot(db_session_factory=mock_db_factory)

    sent_activities = []
    mock_turn_context = AsyncMock()
    mock_turn_context.activity = _make_activity("What are the compliance requirements?")
    mock_turn_context.send_activity = AsyncMock(side_effect=lambda a: sent_activities.append(a))

    await bot.on_message_activity(mock_turn_context)

    assert len(sent_activities) == 1
    activity_sent = sent_activities[0]
    assert activity_sent.attachments
    card = activity_sent.attachments[0].content
    assert card["type"] == "AdaptiveCard"


@pytest.mark.asyncio
async def test_bot_sends_not_registered_card(monkeypatch):
    """Unknown UPN → 'not registered' error card."""
    monkeypatch.setattr(
        "services.adapters.copilot.handler.resolve_user",
        AsyncMock(return_value=None),
    )

    mock_db = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db_factory = MagicMock(return_value=mock_db)

    bot = TeamsBot(db_session_factory=mock_db_factory)

    sent_activities = []
    mock_turn_context = AsyncMock()
    mock_turn_context.activity = _make_activity("Any question", upn="stranger@example.com")
    mock_turn_context.send_activity = AsyncMock(side_effect=lambda a: sent_activities.append(a))

    await bot.on_message_activity(mock_turn_context)

    assert len(sent_activities) == 1
    card = sent_activities[0].attachments[0].content
    texts = [b.get("text", "") for b in card["body"]]
    assert any("Not Registered" in t for t in texts)


@pytest.mark.asyncio
async def test_bot_handles_orchestrator_timeout(monkeypatch):
    """Orchestrator timeout → 'timed out' error card."""
    import httpx

    monkeypatch.setattr(
        "services.adapters.copilot.handler.resolve_user",
        AsyncMock(return_value="user-abc"),
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    monkeypatch.setattr("services.adapters.copilot.handler.httpx.AsyncClient", lambda **kw: mock_client)

    mock_db = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db_factory = MagicMock(return_value=mock_db)

    bot = TeamsBot(db_session_factory=mock_db_factory)

    sent_activities = []
    mock_turn_context = AsyncMock()
    mock_turn_context.activity = _make_activity("Question that times out")
    mock_turn_context.send_activity = AsyncMock(side_effect=lambda a: sent_activities.append(a))

    await bot.on_message_activity(mock_turn_context)

    card = sent_activities[0].attachments[0].content
    texts = [b.get("text", "") for b in card["body"]]
    assert any("Timed Out" in t for t in texts)
