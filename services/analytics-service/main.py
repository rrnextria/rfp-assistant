"""Analytics Service — Win/Loss Learning endpoints.

Routes:
  POST /rfps/{id}/outcome          — record win/loss/no_decision outcome
  GET  /rfps/{id}/outcome          — retrieve recorded outcome
  GET  /admin/insights             — win rate analytics (system_admin only)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Header
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db, get_engine
from common.logging import get_logger
from agents import win_loss_agent

logger = get_logger("analytics-service")

_VALID_OUTCOMES = {"win", "loss", "no_decision"}


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting analytics-service")
    get_engine()
    yield
    await get_engine().dispose()


app = FastAPI(title="analytics-service", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class OutcomeRequest(BaseModel):
    outcome: Literal["win", "loss", "no_decision"]
    notes: str = ""
    lessons_learned: str = ""

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v: str) -> str:
        if v not in _VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of {_VALID_OUTCOMES}")
        return v


class OutcomeResponse(BaseModel):
    record_id: str
    rfp_id: str
    outcome: str
    notes: str
    lessons_learned: str
    score_boosts: dict[str, float]


class InsightsResponse(BaseModel):
    win_rate: float
    total_rfps: int
    wins: int
    losses: int
    no_decisions: int
    top_winning_products: list[dict]
    common_gap_areas: list[dict]


# ---------------------------------------------------------------------------
# RBAC helper (lightweight — reads X-User-Role header)
# ---------------------------------------------------------------------------

def require_system_admin(
    x_user_role: Annotated[str | None, Header()] = None,
) -> str:
    role = x_user_role or ""
    if role != "system_admin":
        raise HTTPException(status_code=403, detail="system_admin role required")
    return role


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "analytics-service"}


# ---------------------------------------------------------------------------
# POST /rfps/{rfp_id}/outcome
# ---------------------------------------------------------------------------

@app.post("/rfps/{rfp_id}/outcome", status_code=201, response_model=OutcomeResponse)
async def record_outcome(
    rfp_id: str,
    req: OutcomeRequest,
    db: AsyncSession = Depends(get_db),
) -> OutcomeResponse:
    """Record a win/loss/no_decision outcome for an RFP."""
    # Verify the RFP exists
    row = await db.execute(
        text("SELECT id FROM rfps WHERE id = :rfp_id"),
        {"rfp_id": rfp_id},
    )
    if not row.fetchone():
        raise HTTPException(status_code=404, detail=f"RFP {rfp_id} not found")

    record_id = await win_loss_agent.learn(
        db=db,
        rfp_id=rfp_id,
        outcome=req.outcome,
        notes=req.notes,
        lessons_learned=req.lessons_learned,
    )

    # Fetch the created record to return full details
    rec = await db.execute(
        text(
            "SELECT id::text, rfp_id::text, outcome, notes, lessons_learned, score_boosts "
            "FROM win_loss_records WHERE id = :id"
        ),
        {"id": record_id},
    )
    r = rec.mappings().one()
    return OutcomeResponse(
        record_id=r["id"],
        rfp_id=r["rfp_id"],
        outcome=r["outcome"],
        notes=r["notes"] or "",
        lessons_learned=r["lessons_learned"] or "",
        score_boosts=r["score_boosts"] or {},
    )


# ---------------------------------------------------------------------------
# GET /rfps/{rfp_id}/outcome
# ---------------------------------------------------------------------------

@app.get("/rfps/{rfp_id}/outcome", response_model=OutcomeResponse)
async def get_outcome(
    rfp_id: str,
    db: AsyncSession = Depends(get_db),
) -> OutcomeResponse:
    """Return the most recent outcome recorded for an RFP."""
    rec = await db.execute(
        text(
            "SELECT id::text, rfp_id::text, outcome, notes, lessons_learned, score_boosts "
            "FROM win_loss_records "
            "WHERE rfp_id = :rfp_id "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"rfp_id": rfp_id},
    )
    r = rec.mappings().fetchone()
    if not r:
        raise HTTPException(status_code=404, detail=f"No outcome recorded for RFP {rfp_id}")

    return OutcomeResponse(
        record_id=r["id"],
        rfp_id=r["rfp_id"],
        outcome=r["outcome"],
        notes=r["notes"] or "",
        lessons_learned=r["lessons_learned"] or "",
        score_boosts=r["score_boosts"] or {},
    )


# ---------------------------------------------------------------------------
# GET /admin/insights
# ---------------------------------------------------------------------------

@app.get("/admin/insights", response_model=InsightsResponse)
async def admin_insights(
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_system_admin),
) -> InsightsResponse:
    """Return win rate analytics and top winning products.

    Requires X-User-Role: system_admin header.
    """
    # Overall counts
    counts_row = await db.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE outcome = 'win')        AS wins,
                COUNT(*) FILTER (WHERE outcome = 'loss')       AS losses,
                COUNT(*) FILTER (WHERE outcome = 'no_decision') AS no_decisions,
                COUNT(*)                                        AS total
            FROM win_loss_records
            """
        )
    )
    c = counts_row.mappings().one()
    total = int(c["total"])
    wins = int(c["wins"])
    losses = int(c["losses"])
    no_decisions = int(c["no_decisions"])
    win_rate = round(wins / total, 4) if total > 0 else 0.0

    # Top winning products: sum positive score_boosts from win records
    product_boosts_row = await db.execute(
        text(
            """
            SELECT (boost_entry.key) AS product_id,
                   SUM((boost_entry.value)::float) AS total_boost
            FROM win_loss_records,
                 jsonb_each_text(score_boosts) AS boost_entry
            WHERE outcome = 'win'
              AND score_boosts != '{}'::jsonb
            GROUP BY boost_entry.key
            ORDER BY total_boost DESC
            LIMIT 10
            """
        )
    )
    top_winning_products = [
        {"product_id": row["product_id"], "total_boost": round(float(row["total_boost"]), 4)}
        for row in product_boosts_row.mappings().all()
    ]

    # Common gap areas: flagged questionnaire items from lost RFPs
    gap_areas_row = await db.execute(
        text(
            """
            SELECT req.category, COUNT(*) AS frequency
            FROM win_loss_records wl
            JOIN rfps r ON r.id = wl.rfp_id
            JOIN rfp_requirements req ON req.rfp_id = r.id
            JOIN questionnaire_items qi ON qi.rfp_requirement_id = req.id
            WHERE wl.outcome = 'loss'
              AND qi.flagged = true
              AND req.category IS NOT NULL
            GROUP BY req.category
            ORDER BY frequency DESC
            LIMIT 10
            """
        )
    )
    common_gap_areas = [
        {"category": row["category"], "frequency": int(row["frequency"])}
        for row in gap_areas_row.mappings().all()
    ]

    return InsightsResponse(
        win_rate=win_rate,
        total_rfps=total,
        wins=wins,
        losses=losses,
        no_decisions=no_decisions,
        top_winning_products=top_winning_products,
        common_gap_areas=common_gap_areas,
    )
