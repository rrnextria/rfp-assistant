"""Conversation turn handler: parse Teams activity → call orchestrator → send card."""
from __future__ import annotations

import re

import httpx
from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes, Attachment
from sqlalchemy.ext.asyncio import AsyncSession

from common.logging import get_logger

from .adaptive_card import build_adaptive_card, build_error_card
from .auth import (
    COPILOT_DEV_MODE,
    ORCHESTRATOR_URL,
    build_user_context_header,
    get_service_jwt,
    resolve_user,
)

logger = get_logger("copilot-adapter.handler")

_ORCHESTRATOR_TIMEOUT = 30.0  # seconds


def _strip_mention(text: str) -> str:
    """Remove @mention tags from activity text (e.g. '<at>RFP Assistant</at> ...')."""
    cleaned = re.sub(r"<at>[^<]+</at>", "", text or "")
    return cleaned.strip()


def _make_card_attachment(card_dict: dict) -> Attachment:
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card_dict,
    )


class TeamsBot(ActivityHandler):
    """Bot Framework activity handler for the RFP Assistant Teams bot."""

    def __init__(self, db_session_factory) -> None:
        """
        Args:
            db_session_factory: An async callable that returns an AsyncSession,
                e.g. ``async_sessionmaker(engine)``.
        """
        super().__init__()
        self._db_factory = db_session_factory

    # ------------------------------------------------------------------
    # Activity handler
    # ------------------------------------------------------------------

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Handle an incoming Teams message."""
        activity: Activity = turn_context.activity
        upn: str = ""

        # Extract UPN from the From field (Teams populates aadObjectId + upn).
        if activity.from_property:
            # Teams sends the UPN in `from_property.name` for AAD users;
            # fall back to email-like properties.
            aad_id = getattr(activity.from_property, "aad_object_id", None)
            upn = getattr(activity.from_property, "email", "") or ""
            if not upn and activity.from_property.name and "@" in activity.from_property.name:
                upn = activity.from_property.name

        if COPILOT_DEV_MODE:
            # In dev mode accept UPN from activity.from_property.name directly.
            upn = upn or (activity.from_property.name if activity.from_property else "dev@example.com")
            logger.info("DEV MODE: using UPN=%s", upn)

        question_text = _strip_mention(activity.text)
        if not question_text:
            await turn_context.send_activity("Please include a question after mentioning me.")
            return

        logger.info("Received question from UPN=%s: %r", upn, question_text[:120])

        # -- Resolve user identity -----------------------------------------------
        async with self._db_factory() as db:
            user_id = await resolve_user(upn, db)

        if user_id is None:
            card = build_error_card(
                "Not Registered",
                f"Your account ({upn}) is not registered in the RFP Assistant. "
                "Please contact your administrator.",
            )
            await turn_context.send_activity(
                Activity(
                    type=ActivityTypes.message,
                    attachments=[_make_card_attachment(card)],
                )
            )
            return

        # -- Call orchestrator ---------------------------------------------------
        service_jwt = get_service_jwt()
        headers = {
            "Authorization": f"Bearer {service_jwt}",
            **build_user_context_header(user_id),
        }
        payload = {"question": question_text, "mode": "answer"}

        try:
            async with httpx.AsyncClient(timeout=_ORCHESTRATOR_TIMEOUT) as client:
                resp = await client.post(
                    f"{ORCHESTRATOR_URL}/ask",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.warning("Orchestrator request timed out for user=%s", user_id)
            card = build_error_card(
                "Request Timed Out",
                "The RFP Assistant took too long to respond. Please try again in a moment.",
            )
            await turn_context.send_activity(
                Activity(type=ActivityTypes.message, attachments=[_make_card_attachment(card)])
            )
            return
        except httpx.HTTPStatusError as exc:
            logger.error("Orchestrator HTTP error %s for user=%s", exc.response.status_code, user_id)
            card = build_error_card(
                "Service Error",
                "The RFP Assistant service is currently unavailable. Please try again later.",
            )
            await turn_context.send_activity(
                Activity(type=ActivityTypes.message, attachments=[_make_card_attachment(card)])
            )
            return
        except Exception as exc:
            logger.exception("Unexpected error calling orchestrator: %s", exc)
            card = build_error_card("Service Error", "An unexpected error occurred. Please try again.")
            await turn_context.send_activity(
                Activity(type=ActivityTypes.message, attachments=[_make_card_attachment(card)])
            )
            return

        # -- Format and send adaptive card response ------------------------------
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        mode = data.get("mode", "answer")

        card = build_adaptive_card(answer=answer, citations=citations, mode=mode)
        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.message,
                attachments=[_make_card_attachment(card)],
            )
        )
        logger.info(
            "Sent answer card to user=%s (%d citations, confidence=%.2f)",
            user_id,
            len(citations),
            data.get("confidence", 0.0),
        )
