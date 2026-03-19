from __future__ import annotations

import uuid

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.logging import get_logger

logger = get_logger("rfp-service.crud")


class CreateRFPRequest(BaseModel):
    customer: str
    industry: str = ""
    region: str = ""


class UpdateRFPRequest(BaseModel):
    customer: str | None = None
    industry: str | None = None
    region: str | None = None
    status: str | None = None


class AddQuestionsRequest(BaseModel):
    questions: list[str]


# --- RFP CRUD ---

async def create_rfp(db: AsyncSession, req: CreateRFPRequest, user_id: str) -> str:
    rfp_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO rfps (id, customer, industry, region, created_by) "
            "VALUES (:id, :customer, :industry, :region, :user_id)"
        ),
        {"id": rfp_id, "customer": req.customer, "industry": req.industry,
         "region": req.region, "user_id": user_id},
    )
    await db.commit()
    return rfp_id


async def get_rfp(db: AsyncSession, rfp_id: str, user_id: str, role: str) -> dict:
    row = await db.execute(
        text("SELECT id, customer, industry, region, status, created_by, created_at FROM rfps WHERE id = :id"),
        {"id": rfp_id},
    )
    rfp = row.mappings().first()
    if not rfp:
        raise HTTPException(404, "RFP not found")
    if role not in ("system_admin", "content_admin") and str(rfp["created_by"]) != user_id:
        raise HTTPException(403, "Access denied")

    # Get questions with latest answers
    qs = await db.execute(
        text(
            "SELECT q.id, q.question, "
            "a.id as answer_id, a.answer, a.approved, a.version, a.confidence, a.detail_level "
            "FROM rfp_questions q "
            "LEFT JOIN rfp_answers a ON a.question_id = q.id "
            "AND a.version = (SELECT MAX(version) FROM rfp_answers WHERE question_id = q.id) "
            "WHERE q.rfp_id = :rfp_id"
        ),
        {"rfp_id": rfp_id},
    )
    questions = [dict(r) for r in qs.mappings().all()]

    return {
        "id": str(rfp["id"]),
        "customer": rfp["customer"],
        "industry": rfp["industry"],
        "region": rfp["region"],
        "status": rfp.get("status", "draft"),
        "created_at": rfp["created_at"].isoformat() if rfp.get("created_at") else None,
        "questions": questions,
    }


async def update_rfp(
    db: AsyncSession, rfp_id: str, req: UpdateRFPRequest, user_id: str, role: str
) -> dict:
    row = await db.execute(
        text("SELECT id, created_by FROM rfps WHERE id = :id"), {"id": rfp_id}
    )
    rfp = row.mappings().first()
    if not rfp:
        raise HTTPException(404, "RFP not found")
    if role not in ("system_admin", "content_admin") and str(rfp["created_by"]) != user_id:
        raise HTTPException(403, "Access denied")

    updates = []
    params: dict = {"id": rfp_id}
    if req.customer is not None:
        updates.append("customer = :customer")
        params["customer"] = req.customer
    if req.industry is not None:
        updates.append("industry = :industry")
        params["industry"] = req.industry
    if req.region is not None:
        updates.append("region = :region")
        params["region"] = req.region
    if req.status is not None:
        if req.status not in ("draft", "approved", "in_review"):
            raise HTTPException(400, "Invalid status")
        updates.append("status = :status")
        params["status"] = req.status

    if updates:
        await db.execute(
            text(f"UPDATE rfps SET {', '.join(updates)} WHERE id = :id"),
            params,
        )
        await db.commit()

    return {"rfp_id": rfp_id, "updated": True}


async def delete_rfp(db: AsyncSession, rfp_id: str, user_id: str, role: str) -> None:
    row = await db.execute(
        text("SELECT id, created_by FROM rfps WHERE id = :id"), {"id": rfp_id}
    )
    rfp = row.mappings().first()
    if not rfp:
        raise HTTPException(404, "RFP not found")
    if role not in ("system_admin", "content_admin") and str(rfp["created_by"]) != user_id:
        raise HTTPException(403, "Access denied")

    # Cascade: delete answers → questions → rfp
    await db.execute(
        text(
            "DELETE FROM rfp_answers WHERE question_id IN "
            "(SELECT id FROM rfp_questions WHERE rfp_id = :id)"
        ),
        {"id": rfp_id},
    )
    await db.execute(text("DELETE FROM rfp_questions WHERE rfp_id = :id"), {"id": rfp_id})
    await db.execute(text("DELETE FROM rfps WHERE id = :id"), {"id": rfp_id})
    await db.commit()


async def list_rfps(
    db: AsyncSession, user_id: str, role: str = "end_user", limit: int = 50, offset: int = 0
) -> list[dict]:
    if role in ("system_admin", "content_admin"):
        rows = await db.execute(
            text(
                "SELECT id, customer, industry, region, status, created_at "
                "FROM rfps ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset},
        )
    else:
        rows = await db.execute(
            text(
                "SELECT id, customer, industry, region, status, created_at "
                "FROM rfps WHERE created_by = :uid "
                "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            ),
            {"uid": user_id, "limit": limit, "offset": offset},
        )
    result = []
    for r in rows.mappings().all():
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        d["id"] = str(d["id"])
        result.append(d)
    return result


async def add_questions(
    db: AsyncSession, rfp_id: str, questions: list[str], user_id: str, role: str
) -> list[str]:
    row = await db.execute(
        text("SELECT created_by FROM rfps WHERE id = :id"), {"id": rfp_id}
    )
    rfp = row.mappings().first()
    if not rfp:
        raise HTTPException(404, "RFP not found")
    if role not in ("system_admin", "content_admin") and str(rfp["created_by"]) != user_id:
        raise HTTPException(403, "Access denied")

    ids = []
    for q in questions:
        qid = str(uuid.uuid4())
        await db.execute(
            text("INSERT INTO rfp_questions (id, rfp_id, question) VALUES (:id, :rfp_id, :q)"),
            {"id": qid, "rfp_id": rfp_id, "q": q},
        )
        ids.append(qid)
    await db.commit()
    return ids


async def generate_answer(
    db: AsyncSession, rfp_id: str, question_id: str, detail_level: str, user_context: dict
) -> str:
    """Call ask_pipeline and store result as rfp_answer version 1 (or N+1)."""
    row = await db.execute(
        text("SELECT question FROM rfp_questions WHERE id = :id AND rfp_id = :rfp_id"),
        {"id": question_id, "rfp_id": rfp_id},
    )
    q = row.mappings().first()
    if not q:
        raise HTTPException(404, "Question not found")

    import os
    import httpx

    orchestrator_url = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{orchestrator_url}/ask",
                json={
                    "question": q["question"],
                    "mode": "draft",
                    "detail_level": detail_level,
                    "rfp_id": rfp_id,
                    "user_context": user_context,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error(f"Orchestrator call failed: {exc}")
        raise HTTPException(502, "Failed to generate answer — orchestrator unavailable")

    answer_text = data.get("answer", "")
    confidence = data.get("confidence", 0.0)
    citations = data.get("citations", [])
    partial = len(citations) < 2

    ver_row = await db.execute(
        text("SELECT MAX(version) as max_v FROM rfp_answers WHERE question_id = :qid"),
        {"qid": question_id},
    )
    ver = ver_row.scalar() or 0
    new_version = ver + 1

    answer_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO rfp_answers (id, question_id, answer, approved, version, confidence, detail_level, partial_compliance) "
            "VALUES (:id, :qid, :answer, false, :version, :confidence, :detail_level, :partial)"
        ),
        {
            "id": answer_id,
            "qid": question_id,
            "answer": answer_text,
            "version": new_version,
            "confidence": confidence,
            "detail_level": detail_level,
            "partial": partial,
        },
    )
    await db.commit()
    return answer_id


async def regenerate_all_answers(
    db: AsyncSession, rfp_id: str, detail_level: str = "balanced", user_context: dict = {}
) -> dict:
    """Regenerate answers for all questions in an RFP. Returns counts."""
    rows = await db.execute(
        text("SELECT id FROM rfp_questions WHERE rfp_id = :rfp_id ORDER BY created_at"),
        {"rfp_id": rfp_id},
    )
    question_ids = [str(r["id"]) for r in rows.mappings().all()]

    succeeded = 0
    failed = 0
    for qid in question_ids:
        try:
            await generate_answer(db, rfp_id, qid, detail_level, user_context)
            succeeded += 1
        except Exception as exc:
            logger.error(f"Failed to regenerate answer for question {qid}: {exc}")
            failed += 1

    return {"regenerated": succeeded, "failed": failed, "total": len(question_ids)}


async def update_answer(
    db: AsyncSession, question_id: str, answer_id: str, answer_text: str, expected_version: int
) -> str:
    row = await db.execute(
        text("SELECT MAX(version) as max_v FROM rfp_answers WHERE question_id = :qid"),
        {"qid": question_id},
    )
    current_version = row.scalar() or 0
    if current_version != expected_version:
        raise HTTPException(409, f"Version conflict: expected {expected_version}, got {current_version}")

    new_answer_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO rfp_answers (id, question_id, answer, approved, version) "
            "VALUES (:id, :qid, :answer, false, :version)"
        ),
        {"id": new_answer_id, "qid": question_id, "answer": answer_text, "version": current_version + 1},
    )
    await db.commit()
    return new_answer_id


async def approve_answer(db: AsyncSession, answer_id: str) -> None:
    await db.execute(
        text("UPDATE rfp_answers SET approved = true WHERE id = :id"),
        {"id": answer_id},
    )
    await db.commit()
