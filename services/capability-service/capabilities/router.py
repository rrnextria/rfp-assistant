"""FastAPI routers mounted under /capabilities/*."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db

from . import crud
from .schemas import (CertificationIn, CertificationOut, GeographyIn, GeographyOut,
                       IndustryIn, IndustryOut, ServiceLineIn, ServiceLineOut)


def _tenant(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=401, detail="X-Tenant-Id header required")
    return x_tenant_id


# --- industries ---
industries_router = APIRouter(prefix="/capabilities/industries", tags=["capabilities"])


@industries_router.post("", status_code=201, response_model=IndustryOut)
async def create_industry(req: IndustryIn,
                           tenant_id: str = Depends(_tenant),
                           db: AsyncSession = Depends(get_db)):
    return await crud.create_industry(db, tenant_id, req.name)


@industries_router.get("", response_model=list[IndustryOut])
async def list_industries(tenant_id: str = Depends(_tenant),
                            db: AsyncSession = Depends(get_db)):
    return await crud.list_industries(db, tenant_id)


@industries_router.patch("/{ind_id}", response_model=IndustryOut)
async def patch_industry(ind_id: str, req: IndustryIn,
                          tenant_id: str = Depends(_tenant),
                          db: AsyncSession = Depends(get_db)):
    row = await crud.patch_industry(db, tenant_id, ind_id, req.name)
    if not row:
        raise HTTPException(404, "Not found")
    return row


@industries_router.delete("/{ind_id}", status_code=204)
async def delete_industry(ind_id: str,
                           tenant_id: str = Depends(_tenant),
                           db: AsyncSession = Depends(get_db)):
    if not await crud.delete_industry(db, tenant_id, ind_id):
        raise HTTPException(404, "Not found")


# --- geographies ---
geographies_router = APIRouter(prefix="/capabilities/geographies", tags=["capabilities"])


@geographies_router.post("", status_code=201, response_model=GeographyOut)
async def create_geography(req: GeographyIn,
                            tenant_id: str = Depends(_tenant),
                            db: AsyncSession = Depends(get_db)):
    return await crud.create_geography(db, tenant_id, req.name, req.type, req.parent_id)


@geographies_router.get("", response_model=list[GeographyOut])
async def list_geographies(tenant_id: str = Depends(_tenant),
                            db: AsyncSession = Depends(get_db)):
    return await crud.list_geographies(db, tenant_id)


@geographies_router.patch("/{geo_id}", response_model=GeographyOut)
async def patch_geography(geo_id: str, req: GeographyIn,
                           tenant_id: str = Depends(_tenant),
                           db: AsyncSession = Depends(get_db)):
    row = await crud.patch_geography(db, tenant_id, geo_id, name=req.name,
                                       type=req.type, parent_id=req.parent_id)
    if not row:
        raise HTTPException(404, "Not found")
    return row


@geographies_router.delete("/{geo_id}", status_code=204)
async def delete_geography(geo_id: str,
                            tenant_id: str = Depends(_tenant),
                            db: AsyncSession = Depends(get_db)):
    if not await crud.delete_geography(db, tenant_id, geo_id):
        raise HTTPException(404, "Not found")


# --- certifications ---
certifications_router = APIRouter(prefix="/capabilities/certifications", tags=["capabilities"])


@certifications_router.post("", status_code=201, response_model=CertificationOut)
async def create_certification(req: CertificationIn,
                                 tenant_id: str = Depends(_tenant),
                                 db: AsyncSession = Depends(get_db)):
    return await crud.create_certification(db, tenant_id, req.name, req.issuing_body,
                                              req.scope, req.expires_at, req.evidence_doc_id)


@certifications_router.get("", response_model=list[CertificationOut])
async def list_certifications(tenant_id: str = Depends(_tenant),
                                db: AsyncSession = Depends(get_db)):
    return await crud.list_certifications(db, tenant_id)


@certifications_router.patch("/{cert_id}", response_model=CertificationOut)
async def patch_certification(cert_id: str, req: CertificationIn,
                                tenant_id: str = Depends(_tenant),
                                db: AsyncSession = Depends(get_db)):
    row = await crud.patch_certification(db, tenant_id, cert_id, name=req.name,
                                            issuing_body=req.issuing_body, scope=req.scope,
                                            expires_at=req.expires_at,
                                            evidence_doc_id=req.evidence_doc_id)
    if not row:
        raise HTTPException(404, "Not found")
    return row


@certifications_router.delete("/{cert_id}", status_code=204)
async def delete_certification(cert_id: str,
                                 tenant_id: str = Depends(_tenant),
                                 db: AsyncSession = Depends(get_db)):
    if not await crud.delete_certification(db, tenant_id, cert_id):
        raise HTTPException(404, "Not found")


# --- service_lines ---
service_lines_router = APIRouter(prefix="/capabilities/service-lines", tags=["capabilities"])


@service_lines_router.post("", status_code=201, response_model=ServiceLineOut)
async def create_service_line(req: ServiceLineIn,
                                tenant_id: str = Depends(_tenant),
                                db: AsyncSession = Depends(get_db)):
    return await crud.create_service_line(db, tenant_id, req.name, req.description,
                                             req.parent_id, req.industry_ids, req.geography_ids)


@service_lines_router.get("", response_model=list[ServiceLineOut])
async def list_service_lines(tenant_id: str = Depends(_tenant),
                                db: AsyncSession = Depends(get_db)):
    return await crud.list_service_lines(db, tenant_id)


@service_lines_router.delete("/{sl_id}", status_code=204)
async def delete_service_line(sl_id: str,
                                tenant_id: str = Depends(_tenant),
                                db: AsyncSession = Depends(get_db)):
    if not await crud.delete_service_line(db, tenant_id, sl_id):
        raise HTTPException(404, "Not found")
