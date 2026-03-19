from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import get_settings
from common.db import get_db, get_engine, get_session_factory
from common.logging import get_logger
from questionnaire import QuestionnaireCompletionAgent
from rfp_crud import (
    AddQuestionsRequest,
    CreateRFPRequest,
    UpdateRFPRequest,
    add_questions,
    approve_answer,
    create_rfp,
    delete_rfp,
    generate_answer,
    get_rfp,
    list_rfps,
    regenerate_all_answers,
    update_answer,
    update_rfp,
)

logger = get_logger("rfp-service")
q_agent = QuestionnaireCompletionAgent()


@dataclass
class CallerIdentity:
    user_id: str
    role: str


def _get_caller(request: Request) -> CallerIdentity:
    """Decode JWT from the Authorization header forwarded by the gateway."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            from jose import jwt
            settings = get_settings()
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            return CallerIdentity(user_id=payload.get("sub", ""), role=payload.get("role", "end_user"))
        except Exception:
            pass
    return CallerIdentity(user_id="", role="system_admin")


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
    request: Request,
    req: CreateRFPRequest,
    db: AsyncSession = Depends(get_db),
):
    caller = _get_caller(request)
    rfp_id = await create_rfp(db, req, user_id=caller.user_id or "00000000-0000-0000-0000-000000000000")
    return {"rfp_id": rfp_id}


@app.get("/rfps/{rfp_id}")
async def get_rfp_endpoint(
    request: Request,
    rfp_id: str,
    db: AsyncSession = Depends(get_db),
):
    caller = _get_caller(request)
    return await get_rfp(db, rfp_id, user_id=caller.user_id, role=caller.role)


@app.patch("/rfps/{rfp_id}")
async def update_rfp_endpoint(
    request: Request,
    rfp_id: str,
    req: UpdateRFPRequest,
    db: AsyncSession = Depends(get_db),
):
    caller = _get_caller(request)
    return await update_rfp(db, rfp_id, req, user_id=caller.user_id, role=caller.role)


@app.delete("/rfps/{rfp_id}", status_code=204)
async def delete_rfp_endpoint(
    request: Request,
    rfp_id: str,
    db: AsyncSession = Depends(get_db),
):
    caller = _get_caller(request)
    await delete_rfp(db, rfp_id, user_id=caller.user_id, role=caller.role)


class RegenerateAllRequest(BaseModel):
    detail_level: Literal["minimal", "balanced", "detailed"] = "balanced"
    user_context: dict = {}


@app.post("/rfps/{rfp_id}/regenerate-all", status_code=202)
async def regenerate_all_endpoint(
    rfp_id: str,
    req: RegenerateAllRequest,
    background_tasks: BackgroundTasks,
):
    async def _run():
        factory = get_session_factory()
        async with factory() as db:
            await regenerate_all_answers(db, rfp_id, req.detail_level, req.user_context)

    background_tasks.add_task(_run)
    return {"status": "regenerating", "rfp_id": rfp_id}


@app.get("/rfps")
async def list_rfps_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    caller = _get_caller(request)
    return await list_rfps(db, user_id=caller.user_id, role=caller.role, limit=limit, offset=offset)


# --- Questions ---

@app.get("/rfps/{rfp_id}/questions")
async def list_questions_endpoint(
    rfp_id: str,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text as sqlt
    rows = await db.execute(
        sqlt("SELECT id, rfp_id, question FROM rfp_questions WHERE rfp_id = :rfp_id ORDER BY created_at"),
        {"rfp_id": rfp_id},
    )
    return [{"id": str(r["id"]), "rfp_id": str(r["rfp_id"]), "question": r["question"]}
            for r in rows.mappings().all()]


@app.post("/rfps/{rfp_id}/questions", status_code=201)
async def add_questions_endpoint(
    request: Request,
    rfp_id: str,
    req: AddQuestionsRequest,
    db: AsyncSession = Depends(get_db),
):
    caller = _get_caller(request)
    ids = await add_questions(db, rfp_id, req.questions, user_id=caller.user_id, role=caller.role)
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


@app.get("/rfps/{rfp_id}/questions/{question_id}/answers/latest")
async def get_latest_answer_endpoint(
    rfp_id: str,
    question_id: str,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text as sqlt
    row = await db.execute(
        sqlt(
            "SELECT id, question_id, answer, approved, version, confidence, detail_level, partial_compliance "
            "FROM rfp_answers WHERE question_id = :qid ORDER BY version DESC LIMIT 1"
        ),
        {"qid": question_id},
    )
    r = row.mappings().first()
    if not r:
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(404, "No answer found")
    return dict(r)


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
