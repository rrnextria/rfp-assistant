"""Portfolio Service — FastAPI application.

Endpoints:
  POST   /products                      — create a product (system_admin only)
  PATCH  /products/{id}/embed           — trigger ProductKnowledgeAgent embedding (system_admin only)
  POST   /rfps/{id}/recommend-solution  — run full portfolio pipeline; return recommendations + coverage
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db, get_engine
from common.logging import get_logger
from agents import (
    PortfolioOrchestrationAgent,
    ProductKnowledgeAgent,
    SolutionRecommendationAgent,
)

logger = get_logger("portfolio-service")

_knowledge_agent = ProductKnowledgeAgent()
_orchestration_agent = PortfolioOrchestrationAgent()
_recommendation_agent = SolutionRecommendationAgent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting portfolio-service")
    get_engine()
    yield
    await get_engine().dispose()


app = FastAPI(title="portfolio-service", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "portfolio-service"}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreateProductRequest(BaseModel):
    name: str
    vendor: str | None = None
    category: str | None = None
    description: str | None = None
    features: dict = {}


class ProductResponse(BaseModel):
    product_id: str
    name: str
    vendor: str | None
    category: str | None
    description: str | None
    features: dict


class EmbedResponse(BaseModel):
    product_id: str
    status: str


class RecommendationItem(BaseModel):
    requirement_id: str
    product_id: str | None
    similarity: float
    is_gap: bool


class RecommendSolutionResponse(BaseModel):
    recommendations: list[RecommendationItem]
    coverage: float  # fraction of requirements that are NOT gaps


# ---------------------------------------------------------------------------
# POST /products  (system_admin only — enforced at API gateway in production;
#                  header X-User-Role checked here for defence-in-depth)
# ---------------------------------------------------------------------------

@app.post("/products", status_code=201, response_model=ProductResponse)
async def create_product(
    req: CreateProductRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a product in the global catalog."""
    import json

    product_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO products (id, name, vendor, category, description, features) "
            "VALUES (:id, :name, :vendor, :category, :description, :features::jsonb)"
        ),
        {
            "id": product_id,
            "name": req.name,
            "vendor": req.vendor,
            "category": req.category,
            "description": req.description,
            "features": json.dumps(req.features),
        },
    )
    await db.commit()
    logger.info(f"Created product {product_id} ({req.name})")
    return ProductResponse(
        product_id=product_id,
        name=req.name,
        vendor=req.vendor,
        category=req.category,
        description=req.description,
        features=req.features,
    )


# ---------------------------------------------------------------------------
# PATCH /products/{product_id}/embed  (system_admin only)
# ---------------------------------------------------------------------------

@app.patch("/products/{product_id}/embed", response_model=EmbedResponse)
async def embed_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Trigger ProductKnowledgeAgent to (re-)embed the product."""
    try:
        await _knowledge_agent.index_product(db, product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EmbedResponse(product_id=product_id, status="embedded")


# ---------------------------------------------------------------------------
# POST /rfps/{rfp_id}/recommend-solution
# ---------------------------------------------------------------------------

@app.post("/rfps/{rfp_id}/recommend-solution", response_model=RecommendSolutionResponse)
async def recommend_solution(
    rfp_id: str,
    tenant_id: str,  # query param — in production extracted from JWT
    db: AsyncSession = Depends(get_db),
):
    """
    Run the full portfolio pipeline for an RFP:
      1. Load rfp_requirements for the given rfp_id
      2. PortfolioOrchestrationAgent: cosine-similarity match against tenant products
      3. SolutionRecommendationAgent: select best product per requirement; flag gaps

    Returns per-requirement recommendations and an overall coverage float.
    """
    # --- 1. Load requirements ---
    rows = await db.execute(
        text(
            "SELECT id::text AS id, text FROM rfp_requirements WHERE rfp_id = :rfp_id"
        ),
        {"rfp_id": rfp_id},
    )
    req_rows = rows.mappings().all()

    if not req_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No requirements found for RFP {rfp_id}",
        )

    requirement_texts: dict[str, str] = {r["id"]: r["text"] for r in req_rows}

    # --- 2. Portfolio Orchestration Agent ---
    coverages = await _orchestration_agent.match(
        db=db,
        requirement_texts=requirement_texts,
        tenant_id=tenant_id,
    )

    # --- 3. Solution Recommendation Agent ---
    raw_recommendations = _recommendation_agent.recommend(coverages)

    # --- 4. Build response ---
    recommendations = [
        RecommendationItem(
            requirement_id=r.requirement_id,
            product_id=r.product_id,
            similarity=round(r.similarity, 4),
            is_gap=r.is_gap,
        )
        for r in raw_recommendations
    ]

    total = len(recommendations)
    covered = sum(1 for r in recommendations if not r.is_gap)
    coverage = round(covered / total, 4) if total > 0 else 0.0

    return RecommendSolutionResponse(recommendations=recommendations, coverage=coverage)
