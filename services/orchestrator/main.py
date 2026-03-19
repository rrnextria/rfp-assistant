from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db, get_engine
from common.logging import get_logger
from pipeline import ask_pipeline

logger = get_logger("orchestrator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting orchestrator")
    get_engine()
    yield
    await get_engine().dispose()


app = FastAPI(title="orchestrator", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str
    mode: Literal["answer", "draft", "review", "gap"] = "answer"
    detail_level: Literal["minimal", "balanced", "detailed"] = "balanced"
    rfp_id: str | None = None
    stream: bool = False
    user_context: dict = {}


class CitationOut(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str = ""
    snippet: str


class AskResponseOut(BaseModel):
    answer: str
    citations: list[CitationOut]
    confidence: float
    model: str
    partial_compliance: bool = False


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "orchestrator"}


@app.post("/ask", response_model=AskResponseOut)
async def ask(
    req: AskRequest,
    db: AsyncSession = Depends(get_db),
) -> AskResponseOut:
    result = await ask_pipeline(
        question=req.question,
        mode=req.mode,
        detail_level=req.detail_level,
        user_context=req.user_context,
        db=db,
        rfp_id=req.rfp_id,
    )

    return AskResponseOut(
        answer=result.answer,
        citations=[CitationOut(chunk_id=c.chunk_id, doc_id=c.doc_id, doc_title=c.doc_title, snippet=c.snippet) for c in result.citations],
        confidence=result.confidence,
        model=result.model,
    )
