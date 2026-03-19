from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db, get_engine
from common.logging import get_logger
from rbac_filter import UserContext
from retrieve import retrieve

logger = get_logger("retrieval-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting retrieval-service")
    get_engine()
    yield
    await get_engine().dispose()


app = FastAPI(title="retrieval-service", lifespan=lifespan)


class UserContextSchema(BaseModel):
    user_id: str
    role: str
    teams: list[str] = []


class RetrieveRequest(BaseModel):
    query: str
    user_context: UserContextSchema
    filters: dict[str, Any] = {}
    top_n: int = 12
    score_adjustments: dict[str, float] = {}


class ChunkResult(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    score: float
    metadata: dict[str, Any]


class RetrieveResponse(BaseModel):
    chunks: list[ChunkResult]


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "retrieval-service"}


@app.post("/retrieve", response_model=RetrieveResponse)
async def retrieve_endpoint(
    req: RetrieveRequest,
    db: AsyncSession = Depends(get_db),
) -> RetrieveResponse:
    """Internal endpoint: RBAC-filtered hybrid retrieval."""
    user_ctx = UserContext(
        user_id=req.user_context.user_id,
        role=req.user_context.role,
        teams=req.user_context.teams,
    )

    chunks = await retrieve(
        db=db,
        query=req.query,
        user_ctx=user_ctx,
        filters=req.filters,
        top_n=req.top_n,
        score_adjustments=req.score_adjustments or None,
    )

    return RetrieveResponse(
        chunks=[
            ChunkResult(
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                text=c.text,
                score=c.score,
                metadata=c.metadata,
            )
            for c in chunks
        ]
    )
