from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db, get_engine
from common.logging import get_logger
from questionnaire import QuestionnaireCompletionAgent
from rfp_crud import (
    AddQuestionsRequest,
    CreateRFPRequest,
    add_questions,
    approve_answer,
    create_rfp,
    generate_answer,
    get_rfp,
    list_rfps,
    update_answer,
)

logger = get_logger("rfp-service")
q_agent = QuestionnaireCompletionAgent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting rfp-service")
    get_engine()
    yield
    await get_engine().dispose()


app = FastAPI(title="rfp-service", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "rfp-service"}


class GenerateRequest(BaseModel):
    detail_level: Literal["minimal", "balanced", "detailed"] = "balanced"
    user_context: dict = {}


class UpdateAnswerRequest(BaseModel):
    answer: str
    version: int


# --- RFP CRUD ---

@app.post("/rfps", status_code=201)
async def create_rfp_endpoint(
    req: CreateRFPRequest,
    db: AsyncSession = Depends(get_db),
):
    # TODO: get user_id from JWT in production
    rfp_id = await create_rfp(db, req, user_id="system")
    return {"rfp_id": rfp_id}


@app.get("/rfps/{rfp_id}")
async def get_rfp_endpoint(
    rfp_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await get_rfp(db, rfp_id, user_id="system", role="system_admin")


@app.get("/rfps")
async def list_rfps_endpoint(
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    return await list_rfps(db, user_id="system", limit=limit, offset=offset)


# --- Questions ---

@app.post("/rfps/{rfp_id}/questions", status_code=201)
async def add_questions_endpoint(
    rfp_id: str,
    req: AddQuestionsRequest,
    db: AsyncSession = Depends(get_db),
):
    ids = await add_questions(db, rfp_id, req.questions, user_id="system", role="system_admin")
    return {"question_ids": ids}


# --- Answer Generation ---

@app.post("/rfps/{rfp_id}/questions/{question_id}/generate", status_code=201)
async def generate_answer_endpoint(
    rfp_id: str,
    question_id: str,
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    answer_id = await generate_answer(db, rfp_id, question_id, req.detail_level, req.user_context)
    return {"answer_id": answer_id}


@app.patch("/rfps/{rfp_id}/questions/{question_id}/answers/{answer_id}")
async def update_answer_endpoint(
    rfp_id: str,
    question_id: str,
    answer_id: str,
    req: UpdateAnswerRequest,
    db: AsyncSession = Depends(get_db),
):
    new_id = await update_answer(db, question_id, answer_id, req.answer, req.version)
    return {"answer_id": new_id}


@app.post("/rfps/{rfp_id}/questions/{question_id}/answers/{answer_id}/approve")
async def approve_answer_endpoint(
    rfp_id: str,
    question_id: str,
    answer_id: str,
    db: AsyncSession = Depends(get_db),
):
    await approve_answer(db, answer_id)
    return {"status": "approved"}


@app.get("/rfps/{rfp_id}/questions/{question_id}/answers")
async def get_answers_endpoint(
    rfp_id: str,
    question_id: str,
    all_versions: bool = False,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    if all_versions:
        rows = await db.execute(
            text("SELECT id, answer, approved, version, confidence, detail_level FROM rfp_answers WHERE question_id = :qid ORDER BY version DESC"),
            {"qid": question_id},
        )
    else:
        rows = await db.execute(
            text("SELECT id, answer, approved, version, confidence, detail_level FROM rfp_answers WHERE question_id = :qid ORDER BY version DESC LIMIT 1"),
            {"qid": question_id},
        )
    return [dict(r) for r in rows.mappings().all()]


# --- Questionnaire Completion ---

@app.post("/rfps/{rfp_id}/questionnaire/complete")
async def complete_questionnaire(
    rfp_id: str,
    user_context: dict = {},
    db: AsyncSession = Depends(get_db),
):
    result = await q_agent.complete_all_for_rfp(db, rfp_id, user_context)
    return result
