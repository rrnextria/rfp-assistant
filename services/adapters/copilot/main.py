"""FastAPI app for the RFP Assistant Copilot / Teams channel adapter.

Exposes:
  POST /api/messages   — Bot Framework webhook (signed by Microsoft)
  GET  /healthz        — Liveness probe
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity
from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import async_sessionmaker

from common.db import get_engine
from common.logging import get_logger

from .auth import BOT_APP_ID, BOT_APP_PASSWORD
from .handler import TeamsBot

logger = get_logger("copilot-adapter")

# ---------------------------------------------------------------------------
# Bot Framework adapter setup
# ---------------------------------------------------------------------------

_bot_settings = BotFrameworkAdapterSettings(
    app_id=BOT_APP_ID,
    app_password=BOT_APP_PASSWORD,
)
_bot_adapter = BotFrameworkAdapter(_bot_settings)


# Error handler: log and ignore so the framework can send an error reply.
async def _on_error(context, error: Exception):
    logger.exception("BotFrameworkAdapter unhandled error: %s", error)
    await context.send_activity("Sorry, something went wrong.")


_bot_adapter.on_turn_error = _on_error


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------

_db_session_factory = None
_bot: TeamsBot | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_session_factory, _bot
    logger.info("Starting copilot-adapter")
    engine = get_engine()
    _db_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    _bot = TeamsBot(db_session_factory=_db_session_factory)
    yield
    await engine.dispose()
    logger.info("Shutdown copilot-adapter")


app = FastAPI(title="copilot-adapter", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "copilot-adapter"}


@app.post("/api/messages")
async def messages(request: Request) -> Response:
    """Bot Framework webhook endpoint.

    The Bot Framework SDK validates the incoming JWT (signed by Microsoft)
    via BotFrameworkAdapter.process_activity.  Unsigned or tampered requests
    are rejected with HTTP 401 by the SDK before our handler is invoked.
    """
    if _bot is None:
        return Response(status_code=503, content="Service not ready")

    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes)
    except json.JSONDecodeError:
        return Response(status_code=400, content="Invalid JSON")

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    response = Response(status_code=201)

    async def turn_call(turn_context):
        await _bot.on_turn(turn_context)

    await _bot_adapter.process_activity(activity, auth_header, turn_call)

    return response
