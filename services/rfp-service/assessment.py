"""Public /rfps/{id}/assess* endpoints. Delegates the pipeline run to the
orchestrator service; read endpoints query the DB directly."""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db

router = APIRouter(prefix="/rfps", tags=["assessment"])

ORCH_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001")


def _ctx(x_tenant_id: str | None = Header(default=None),
         x_user_id: str | None = Header(default=None)) -> dict:
    if not x_tenant_id:
        raise HTTPException(401, "X-Tenant-Id header required")
    return {"tenant_id": x_tenant_id, "user_id": x_user_id}


@router.post("/{rfp_id}/assess", status_code=202)
async def kick_off(rfp_id: str, ctx: dict = Depends(_ctx)):
    async with httpx.AsyncClient(timeout=600.0) as c:
        r = await c.post(
            f"{ORCH_URL}/assess/run",
            json={"rfp_id": rfp_id},
            headers={"X-Tenant-Id": ctx["tenant_id"],
                     "X-User-Id": ctx["user_id"] or ""},
        )
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@router.get("/{rfp_id}/assess")
async def stream(rfp_id: str, stream: bool = False):
    if not stream:
        raise HTTPException(400,
            "Use ?stream=true for SSE; otherwise GET /rfps/{id}/assessments/latest")

    async def gen():
        async with httpx.AsyncClient(timeout=None) as c:
            try:
                async with c.stream("GET", f"{ORCH_URL}/assess/stream/{rfp_id}") as resp:
                    if resp.status_code != 200:
                        yield f'data: {{"event":"error","code":{resp.status_code}}}\n\n'
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield line + "\n"
                        else:
                            yield "\n"
            except Exception as exc:
                yield f'data: {{"event":"error","detail":"{exc}"}}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/{rfp_id}/assessments")
async def list_assessments(rfp_id: str, ctx: dict = Depends(_ctx),
                              db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        text("SELECT id::text AS id, version, status, verdict, fit_score, "
             "win_probability, generated_at FROM bid_assessments "
             "WHERE rfp_id = :r AND tenant_id = :t ORDER BY version DESC"),
        {"r": rfp_id, "t": ctx["tenant_id"]})
    return [dict(r) for r in rows.mappings().all()]


async def _full_assessment(db, rfp_id, tenant_id, *,
                             assessment_id: str | None = None) -> dict:
    if assessment_id:
        head = await db.execute(
            text("SELECT * FROM bid_assessments WHERE id = :id AND rfp_id = :r "
                 "AND tenant_id = :t"),
            {"id": assessment_id, "r": rfp_id, "t": tenant_id})
    else:
        head = await db.execute(
            text("SELECT * FROM bid_assessments WHERE rfp_id = :r AND tenant_id = :t "
                 "ORDER BY version DESC LIMIT 1"),
            {"r": rfp_id, "t": tenant_id})
    h = head.mappings().first()
    if not h:
        raise HTTPException(404, "Not found")
    aid = str(h["id"])
    head_dict = {k: (str(v) if hasattr(v, "hex") else v) for k, v in h.items()}
    if head_dict.get("generated_at"):
        head_dict["generated_at"] = h["generated_at"].isoformat()
    if head_dict.get("completed_at"):
        head_dict["completed_at"] = h["completed_at"].isoformat() if h["completed_at"] else None
    children: dict = {}
    for child_table, key in (("compliance_items", "compliance"),
                              ("eligibility_checks", "eligibility"),
                              ("risks", "risks"),
                              ("capability_matches", "best_fit")):
        rows = await db.execute(
            text(f"SELECT * FROM {child_table} WHERE assessment_id = :a"),
            {"a": aid})
        out = []
        for r in rows.mappings().all():
            d = {k: (str(v) if hasattr(v, "hex") else v) for k, v in r.items()}
            out.append(d)
        children[key] = out
    return {"head": head_dict, **children}


@router.get("/{rfp_id}/assessments/latest")
async def latest_assessment(rfp_id: str, ctx: dict = Depends(_ctx),
                              db: AsyncSession = Depends(get_db)):
    return await _full_assessment(db, rfp_id, ctx["tenant_id"])


@router.get("/{rfp_id}/assessments/{aid}")
async def get_assessment(rfp_id: str, aid: str, ctx: dict = Depends(_ctx),
                           db: AsyncSession = Depends(get_db)):
    return await _full_assessment(db, rfp_id, ctx["tenant_id"], assessment_id=aid)
