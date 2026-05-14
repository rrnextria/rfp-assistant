"""GET /capabilities/profile — bundles all 5 dimensions for the current tenant."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db

from . import crud

profile_router = APIRouter(prefix="/capabilities", tags=["capabilities"])


def _tenant(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=401, detail="X-Tenant-Id header required")
    return x_tenant_id


@profile_router.get("/profile")
async def get_profile(tenant_id: str = Depends(_tenant),
                       db: AsyncSession = Depends(get_db)) -> dict:
    service_lines = await crud.list_service_lines(db, tenant_id)
    industries = await crud.list_industries(db, tenant_id)
    geographies = await crud.list_geographies(db, tenant_id)
    certifications = await crud.list_certifications(db, tenant_id)
    rows = await db.execute(
        text("SELECT id::text AS id, name, vendor, category FROM products "
             "WHERE tenant_id = :t ORDER BY name"),
        {"t": tenant_id},
    )
    products = [dict(r) for r in rows.mappings().all()]
    return {
        "service_lines": service_lines,
        "industries": industries,
        "geographies": geographies,
        "certifications": certifications,
        "products": products,
    }
