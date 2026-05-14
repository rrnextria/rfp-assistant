"""POST/PATCH/GET /past-proposals and /contracts.

Each POST creates both a documents row (for retrieval) and a typed row.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db
from common.embedder import SentenceTransformerEmbedder

_embedder = SentenceTransformerEmbedder()

past_router = APIRouter(prefix="/past-proposals", tags=["past_proposals"])
contracts_router = APIRouter(prefix="/contracts", tags=["contracts"])


def _ctx(x_tenant_id: str | None = Header(default=None),
         x_user_role: str | None = Header(default=None)) -> dict:
    if not x_tenant_id:
        raise HTTPException(401, "X-Tenant-Id header required")
    return {"tenant_id": x_tenant_id, "role": x_user_role or "end_user"}


def _emb_to_vector(emb: list[float]) -> str:
    return "[" + ",".join(str(v) for v in emb) + "]"


async def _create_document(db: AsyncSession, tenant_id: str, title: str, body: str,
                            category: str, metadata: dict) -> str:
    doc_id = str(uuid.uuid4())
    metadata = {**metadata, "approved": True}
    await db.execute(
        text("INSERT INTO documents (id, tenant_id, title, category, status) "
             "VALUES (:id, :t, :ti, :cat, 'approved')"),
        {"id": doc_id, "t": tenant_id, "ti": title, "cat": category},
    )
    emb = _embedder.embed([body])[0]
    await db.execute(
        text("INSERT INTO chunks (id, document_id, text, metadata, embedding) "
             "VALUES (gen_random_uuid(), :d, :t, CAST(:m AS jsonb), CAST(:e AS vector))"),
        {"d": doc_id, "t": body, "m": json.dumps(metadata),
         "e": _emb_to_vector(emb)},
    )
    return doc_id


# --- past_proposals ---

class PastProposalIn(BaseModel):
    title: str
    body: str
    client_name: str | None = None
    industry_id: str | None = None
    submitted_at: date
    outcome: str = "pending"
    outcome_reason: str | None = None
    value_amount: float | None = None
    value_currency: str | None = None


class PastProposalPatch(BaseModel):
    outcome: str | None = None
    outcome_reason: str | None = None


@past_router.post("", status_code=201)
async def create_past_proposal(req: PastProposalIn,
                                  ctx: dict = Depends(_ctx),
                                  db: AsyncSession = Depends(get_db)):
    if ctx["role"] not in ("content_admin", "system_admin"):
        raise HTTPException(403, "Forbidden")
    if req.outcome not in ("won", "lost", "withdrawn", "pending"):
        raise HTTPException(400, "Invalid outcome")
    md = {"client_name": req.client_name, "outcome": req.outcome,
          "submitted_at": req.submitted_at.isoformat()}
    doc_id = await _create_document(db, ctx["tenant_id"], req.title, req.body,
                                       "past_proposal", md)
    pp_id = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO past_proposals (id, tenant_id, document_id, client_name, "
             "industry_id, submitted_at, outcome, outcome_reason, "
             "value_amount, value_currency) "
             "VALUES (:i, :t, :d, :c, :ind, :s, :o, :r, :v, :cu)"),
        {"i": pp_id, "t": ctx["tenant_id"], "d": doc_id, "c": req.client_name,
         "ind": req.industry_id, "s": req.submitted_at, "o": req.outcome,
         "r": req.outcome_reason, "v": req.value_amount, "cu": req.value_currency},
    )
    await db.commit()
    return {"id": pp_id, "document_id": doc_id, "outcome": req.outcome}


@past_router.patch("/{pp_id}")
async def patch_past_proposal(pp_id: str, req: PastProposalPatch,
                                 ctx: dict = Depends(_ctx),
                                 db: AsyncSession = Depends(get_db)):
    if ctx["role"] not in ("content_admin", "system_admin"):
        raise HTTPException(403, "Forbidden")
    sets, params = [], {"id": pp_id, "t": ctx["tenant_id"]}
    if req.outcome is not None:
        if req.outcome not in ("won", "lost", "withdrawn", "pending"):
            raise HTTPException(400, "Invalid outcome")
        sets.append("outcome = :o")
        params["o"] = req.outcome
    if req.outcome_reason is not None:
        sets.append("outcome_reason = :r")
        params["r"] = req.outcome_reason
    if not sets:
        raise HTTPException(400, "No fields to update")
    sql = (f"UPDATE past_proposals SET {', '.join(sets)} "
           "WHERE id = :id AND tenant_id = :t "
           "RETURNING id::text AS id, outcome, outcome_reason")
    r = await db.execute(text(sql), params)
    row = r.mappings().first()
    if not row:
        raise HTTPException(404, "Not found")
    await db.commit()
    return dict(row)


@past_router.get("")
async def list_past_proposals(outcome: str | None = None,
                                industry_id: str | None = None,
                                ctx: dict = Depends(_ctx),
                                db: AsyncSession = Depends(get_db)):
    sql = ("SELECT id::text AS id, document_id::text AS document_id, client_name, "
           "outcome, submitted_at FROM past_proposals WHERE tenant_id = :t")
    params: dict = {"t": ctx["tenant_id"]}
    if outcome:
        sql += " AND outcome = :o"
        params["o"] = outcome
    if industry_id:
        sql += " AND industry_id = :i"
        params["i"] = industry_id
    sql += " ORDER BY submitted_at DESC LIMIT 100"
    rows = await db.execute(text(sql), params)
    return [dict(r) for r in rows.mappings().all()]


# --- contracts ---

class ContractIn(BaseModel):
    title: str
    body: str
    client_name: str
    effective_date: date
    expires_at: date | None = None
    value_amount: float | None = None
    value_currency: str | None = None


@contracts_router.post("", status_code=201)
async def create_contract(req: ContractIn,
                            ctx: dict = Depends(_ctx),
                            db: AsyncSession = Depends(get_db)):
    if ctx["role"] not in ("content_admin", "system_admin"):
        raise HTTPException(403, "Forbidden")
    md = {"client_name": req.client_name,
          "effective_date": req.effective_date.isoformat()}
    doc_id = await _create_document(db, ctx["tenant_id"], req.title, req.body,
                                       "contract", md)
    c_id = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO contracts (id, tenant_id, document_id, client_name, "
             "effective_date, expires_at, value_amount, value_currency) "
             "VALUES (:i, :t, :d, :c, :ef, :ex, :v, :cu)"),
        {"i": c_id, "t": ctx["tenant_id"], "d": doc_id, "c": req.client_name,
         "ef": req.effective_date, "ex": req.expires_at,
         "v": req.value_amount, "cu": req.value_currency},
    )
    await db.commit()
    return {"id": c_id, "document_id": doc_id}


@contracts_router.get("")
async def list_contracts(expires_before: date | None = None,
                          ctx: dict = Depends(_ctx),
                          db: AsyncSession = Depends(get_db)):
    sql = ("SELECT id::text AS id, document_id::text AS document_id, client_name, "
           "effective_date, expires_at FROM contracts WHERE tenant_id = :t")
    params: dict = {"t": ctx["tenant_id"]}
    if expires_before:
        sql += " AND expires_at <= :e"
        params["e"] = expires_before
    sql += " ORDER BY effective_date DESC LIMIT 100"
    rows = await db.execute(text(sql), params)
    return [dict(r) for r in rows.mappings().all()]
