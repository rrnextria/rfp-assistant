from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import get_settings
from common.db import get_db, get_engine
from common.logging import get_logger
from pipeline import ask_pipeline, call_retrieval_service

from assessment import stream as sse
from assessment.agents_bestfit import run_bestfit
from assessment.agents_compliance import run_compliance
from assessment.agents_eligibility import run_eligibility
from assessment.agents_risk import run_risks
from assessment.agents_summary import generate_summary_prose
from assessment.pipeline import BidAssessmentPipeline

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


# ---------------------------------------------------------------------------
# Bid assessment endpoints
# ---------------------------------------------------------------------------

def _ctx(x_tenant_id: str | None = Header(default=None),
         x_user_id: str | None = Header(default=None)) -> dict:
    if not x_tenant_id:
        raise HTTPException(401, "X-Tenant-Id header required")
    return {"tenant_id": x_tenant_id, "user_id": x_user_id}


def _make_llm_client():
    """Best-effort LLM adapter: Claude > OpenAI > None.

    Agents tolerate None by returning empty result sets (status='unknown',
    etc.), which the pipeline still persists as a `partial` assessment.
    """
    s = get_settings()
    try:
        if getattr(s, "anthropic_api_key", None):
            from claude import ClaudeAdapter
            return ClaudeAdapter(api_key=s.anthropic_api_key,
                                  model="claude-sonnet-4-6")
    except Exception:
        pass
    try:
        if getattr(s, "openai_api_key", None):
            from openai_adapter import OpenAIAdapter
            return OpenAIAdapter(api_key=s.openai_api_key, model="gpt-4o")
    except Exception:
        pass
    return None


@app.post("/assess/run")
async def assess_run(
    body: dict = Body(...),
    ctx: dict = Depends(_ctx),
    db: AsyncSession = Depends(get_db),
):
    rfp_id = body.get("rfp_id")
    if not rfp_id:
        raise HTTPException(400, "rfp_id required")

    cap_url = os.environ.get("CAPABILITY_SERVICE_URL",
                              "http://capability-service:8010")
    llm = _make_llm_client()

    async def _compliance_fn(requirements, tenant_id):
        return await run_compliance(
            rfp_id=rfp_id, requirements=requirements, tenant_id=tenant_id,
            retrieval_call=call_retrieval_service, llm_client=llm)

    async def _elig_fn(raw_text, tenant_id):
        return await run_eligibility(
            rfp_id=rfp_id, raw_text=raw_text, tenant_id=tenant_id,
            capability_url=cap_url, llm_client=llm)

    async def _bestfit_fn(requirements, tenant_id):
        return await run_bestfit(
            requirements=requirements, tenant_id=tenant_id,
            capability_url=cap_url)

    async def _risk_fn(raw_text, requirements, compliance, eligibility, best_fit):
        return await run_risks(
            raw_text=raw_text, requirements=requirements,
            compliance=compliance, eligibility=eligibility,
            best_fit=best_fit, llm_client=llm)

    async def _summary_fn(rollup, compliance, eligibility, risks):
        return await generate_summary_prose(
            rollup=rollup, compliance=compliance, eligibility=eligibility,
            risks=risks, llm_client=llm)

    pipeline = BidAssessmentPipeline(
        compliance_agent=_compliance_fn,
        eligibility_agent=_elig_fn,
        bestfit_agent=_bestfit_fn,
        risk_agent=_risk_fn,
        summary_agent=_summary_fn,
        analytics_boost=0.0,
        thresholds={"bid_min_fit": 0.7, "no_bid_max_fit": 0.4},
        mandatory_penalty=0.3,
    )
    return await pipeline.run(
        db=db, rfp_id=rfp_id,
        tenant_id=ctx["tenant_id"], user_id=ctx["user_id"])


@app.get("/assess/stream/{rfp_id}")
async def assess_stream(rfp_id: str, request: Request,
                          db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        sqltext("SELECT version FROM bid_assessments WHERE rfp_id = :r "
                "ORDER BY version DESC LIMIT 1"),
        {"r": rfp_id})
    v = row.scalar()
    if v is None:
        raise HTTPException(404, "No assessment for this RFP")
    v = int(v)
    queue = sse.attach_listener(rfp_id, v)
    backlog = sse.replay(rfp_id, v)

    async def gen():
        try:
            for e in backlog:
                yield sse.format_sse(e)
            while True:
                if await request.is_disconnected():
                    break
                e = await queue.get()
                yield sse.format_sse(e)
                if e.get("event") in ("close", "complete"):
                    break
        finally:
            sse.detach_listener(rfp_id, v, queue)

    return StreamingResponse(gen(), media_type="text/event-stream")
