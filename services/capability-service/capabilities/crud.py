"""DB helpers for capability dimensions.

One module, one set of patterns across all four dimensions — keep the
duplication shallow so the SQL stays readable.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# --- industries ---

async def create_industry(db: AsyncSession, tenant_id: str, name: str) -> dict:
    new_id = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO industries (id, tenant_id, name) VALUES (:id, :t, :n)"),
        {"id": new_id, "t": tenant_id, "n": name},
    )
    await db.commit()
    return {"id": new_id, "name": name}


async def list_industries(db: AsyncSession, tenant_id: str) -> list[dict]:
    rows = await db.execute(
        text("SELECT id::text AS id, name FROM industries "
             "WHERE tenant_id = :t ORDER BY name"),
        {"t": tenant_id},
    )
    return [dict(r) for r in rows.mappings().all()]


async def patch_industry(db: AsyncSession, tenant_id: str, ind_id: str, name: str) -> dict | None:
    result = await db.execute(
        text("UPDATE industries SET name = :n WHERE id = :id AND tenant_id = :t "
             "RETURNING id::text AS id, name"),
        {"n": name, "id": ind_id, "t": tenant_id},
    )
    row = result.mappings().first()
    if not row:
        return None
    await db.commit()
    return dict(row)


async def delete_industry(db: AsyncSession, tenant_id: str, ind_id: str) -> bool:
    r = await db.execute(
        text("DELETE FROM industries WHERE id = :id AND tenant_id = :t"),
        {"id": ind_id, "t": tenant_id},
    )
    await db.commit()
    return (r.rowcount or 0) > 0


# --- geographies ---

async def create_geography(db: AsyncSession, tenant_id: str, name: str, type_: str,
                            parent_id: str | None) -> dict:
    new_id = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO geographies (id, tenant_id, name, type, parent_id) "
             "VALUES (:id, :t, :n, :ty, :p)"),
        {"id": new_id, "t": tenant_id, "n": name, "ty": type_, "p": parent_id},
    )
    await db.commit()
    return {"id": new_id, "name": name, "type": type_, "parent_id": parent_id}


async def list_geographies(db: AsyncSession, tenant_id: str) -> list[dict]:
    rows = await db.execute(
        text("SELECT id::text AS id, name, type, parent_id::text AS parent_id "
             "FROM geographies WHERE tenant_id = :t ORDER BY name"),
        {"t": tenant_id},
    )
    return [dict(r) for r in rows.mappings().all()]


async def patch_geography(db: AsyncSession, tenant_id: str, geo_id: str, **fields) -> dict | None:
    sets, params = [], {"id": geo_id, "t": tenant_id}
    for k, v in fields.items():
        if v is not None:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        row = await db.execute(
            text("SELECT id::text AS id, name, type, parent_id::text AS parent_id "
                 "FROM geographies WHERE id = :id AND tenant_id = :t"),
            params,
        )
        r = row.mappings().first()
        return dict(r) if r else None
    sql = (f"UPDATE geographies SET {', '.join(sets)} "
           "WHERE id = :id AND tenant_id = :t "
           "RETURNING id::text AS id, name, type, parent_id::text AS parent_id")
    row = await db.execute(text(sql), params)
    r = row.mappings().first()
    if not r:
        return None
    await db.commit()
    return dict(r)


async def delete_geography(db: AsyncSession, tenant_id: str, geo_id: str) -> bool:
    r = await db.execute(
        text("DELETE FROM geographies WHERE id = :id AND tenant_id = :t"),
        {"id": geo_id, "t": tenant_id},
    )
    await db.commit()
    return (r.rowcount or 0) > 0


# --- certifications ---

async def create_certification(db: AsyncSession, tenant_id: str, name: str,
                                issuing_body: str | None, scope: str | None,
                                expires_at: date | None, evidence_doc_id: str | None) -> dict:
    new_id = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO certifications (id, tenant_id, name, issuing_body, scope, "
             "expires_at, evidence_doc_id) VALUES (:id, :t, :n, :ib, :sc, :ex, :ed)"),
        {"id": new_id, "t": tenant_id, "n": name, "ib": issuing_body,
         "sc": scope, "ex": expires_at, "ed": evidence_doc_id},
    )
    await db.commit()
    return {"id": new_id, "name": name, "issuing_body": issuing_body, "scope": scope,
            "expires_at": expires_at, "evidence_doc_id": evidence_doc_id}


async def list_certifications(db: AsyncSession, tenant_id: str) -> list[dict]:
    rows = await db.execute(
        text("SELECT id::text AS id, name, issuing_body, scope, expires_at, "
             "evidence_doc_id::text AS evidence_doc_id FROM certifications "
             "WHERE tenant_id = :t ORDER BY name"),
        {"t": tenant_id},
    )
    return [dict(r) for r in rows.mappings().all()]


async def patch_certification(db: AsyncSession, tenant_id: str, cert_id: str, **fields) -> dict | None:
    sets, params = [], {"id": cert_id, "t": tenant_id}
    for k, v in fields.items():
        if v is not None:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return await _get_certification(db, tenant_id, cert_id)
    sql = (f"UPDATE certifications SET {', '.join(sets)} "
           "WHERE id = :id AND tenant_id = :t "
           "RETURNING id::text AS id, name, issuing_body, scope, expires_at, "
           "evidence_doc_id::text AS evidence_doc_id")
    row = await db.execute(text(sql), params)
    r = row.mappings().first()
    if not r:
        return None
    await db.commit()
    return dict(r)


async def _get_certification(db: AsyncSession, tenant_id: str, cert_id: str) -> dict | None:
    row = await db.execute(
        text("SELECT id::text AS id, name, issuing_body, scope, expires_at, "
             "evidence_doc_id::text AS evidence_doc_id FROM certifications "
             "WHERE id = :id AND tenant_id = :t"),
        {"id": cert_id, "t": tenant_id},
    )
    r = row.mappings().first()
    return dict(r) if r else None


async def delete_certification(db: AsyncSession, tenant_id: str, cert_id: str) -> bool:
    r = await db.execute(
        text("DELETE FROM certifications WHERE id = :id AND tenant_id = :t"),
        {"id": cert_id, "t": tenant_id},
    )
    await db.commit()
    return (r.rowcount or 0) > 0


# --- service_lines ---

async def create_service_line(db: AsyncSession, tenant_id: str, name: str,
                                description: str | None, parent_id: str | None,
                                industry_ids: list[str], geography_ids: list[str]) -> dict:
    new_id = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO service_lines (id, tenant_id, name, description, parent_id) "
             "VALUES (:id, :t, :n, :d, :p)"),
        {"id": new_id, "t": tenant_id, "n": name, "d": description, "p": parent_id},
    )
    for ind_id in industry_ids:
        await db.execute(
            text("INSERT INTO service_line_industries (service_line_id, industry_id) "
                 "VALUES (:s, :i) ON CONFLICT DO NOTHING"),
            {"s": new_id, "i": ind_id},
        )
    for geo_id in geography_ids:
        await db.execute(
            text("INSERT INTO service_line_geographies (service_line_id, geography_id) "
                 "VALUES (:s, :g) ON CONFLICT DO NOTHING"),
            {"s": new_id, "g": geo_id},
        )
    await db.commit()
    return await _get_service_line(db, tenant_id, new_id)  # type: ignore[return-value]


async def list_service_lines(db: AsyncSession, tenant_id: str) -> list[dict]:
    rows = await db.execute(
        text("SELECT id::text AS id, name, description, parent_id::text AS parent_id "
             "FROM service_lines WHERE tenant_id = :t ORDER BY name"),
        {"t": tenant_id},
    )
    items: list[dict] = []
    for r in rows.mappings().all():
        sl_id = r["id"]
        ind_rows = await db.execute(
            text("SELECT industry_id::text AS id FROM service_line_industries "
                 "WHERE service_line_id = :s"),
            {"s": sl_id},
        )
        geo_rows = await db.execute(
            text("SELECT geography_id::text AS id FROM service_line_geographies "
                 "WHERE service_line_id = :s"),
            {"s": sl_id},
        )
        items.append({
            **dict(r),
            "industry_ids": [x["id"] for x in ind_rows.mappings().all()],
            "geography_ids": [x["id"] for x in geo_rows.mappings().all()],
        })
    return items


async def _get_service_line(db: AsyncSession, tenant_id: str, sl_id: str) -> dict | None:
    row = await db.execute(
        text("SELECT id::text AS id, name, description, parent_id::text AS parent_id "
             "FROM service_lines WHERE id = :id AND tenant_id = :t"),
        {"id": sl_id, "t": tenant_id},
    )
    r = row.mappings().first()
    if not r:
        return None
    ind_rows = await db.execute(
        text("SELECT industry_id::text AS id FROM service_line_industries WHERE service_line_id = :s"),
        {"s": sl_id},
    )
    geo_rows = await db.execute(
        text("SELECT geography_id::text AS id FROM service_line_geographies WHERE service_line_id = :s"),
        {"s": sl_id},
    )
    return {**dict(r),
            "industry_ids": [x["id"] for x in ind_rows.mappings().all()],
            "geography_ids": [x["id"] for x in geo_rows.mappings().all()]}


async def delete_service_line(db: AsyncSession, tenant_id: str, sl_id: str) -> bool:
    r = await db.execute(
        text("DELETE FROM service_lines WHERE id = :id AND tenant_id = :t"),
        {"id": sl_id, "t": tenant_id},
    )
    await db.commit()
    return (r.rowcount or 0) > 0
