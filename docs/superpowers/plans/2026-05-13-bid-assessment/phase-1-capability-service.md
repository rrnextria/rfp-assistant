# Phase 1 — Capability Service Rename + 5-Dimension Profile

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this phase task-by-task.

**Goal:** Rename `portfolio-service` → `capability-service`, atomically drop the legacy `/portfolio/*` route, and add four new capability tables (`service_lines`, `industries`, `geographies`, `certifications`) plus two M2M tables, with full CRUD endpoints and an aggregated `/capabilities/profile` rollup.

**Architecture:** Single Alembic migration (`0011_capability_profile.py`) creates the new tables; service directory rename + gateway route key rename + env var rename happen in the same commit. CRUD endpoints follow the same pattern as the existing `/products` handlers. No frontend changes in this phase — admin UI lands in phase 4. Tenancy is enforced via a new `common/tenancy.py` helper that returns SQL `WHERE` predicates.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x async, Alembic, pgvector (only for `service_lines.embedding`).

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Move (rename) | `services/portfolio-service/` → `services/capability-service/` | All files moved as-is |
| Modify | `services/capability-service/main.py` | Title + log name + lifespan log message |
| Modify | `services/capability-service/pyproject.toml` | `name = "capability-service"` |
| Create | `services/capability-service/capabilities/__init__.py` | Module entry |
| Create | `services/capability-service/capabilities/schemas.py` | Pydantic models for 4 new dimensions |
| Create | `services/capability-service/capabilities/crud.py` | DB helpers per dimension |
| Create | `services/capability-service/capabilities/router.py` | FastAPI routers for `/capabilities/*` |
| Create | `services/capability-service/capabilities/profile.py` | Rollup endpoint `/capabilities/profile` |
| Create | `services/capability-service/capabilities/embedding.py` | Background embed for `service_lines.embedding` |
| Modify | `services/capability-service/main.py` | Include new routers; mount under `/capabilities` |
| Create | `services/capability-service/tests/test_crud_dimensions.py` | Per-dimension CRUD tests |
| Create | `services/capability-service/tests/test_profile_rollup.py` | `/capabilities/profile` rollup |
| Create | `migrations/versions/0011_capability_profile.py` | 4 + 2 new tables; reversible |
| Modify | `services/api-gateway/proxy.py` | Service map: `products` removed, `capabilities` added |
| Modify | `services/api-gateway/auth.py` | JWT now carries `tenant_id`; `get_current_user` returns it |
| Create | `common/common/tenancy.py` | `tenant_scope(query, tenant_id, table)` helper |
| Modify | `docker-compose.yml` | Service block renamed; env var renamed |
| Modify | `services/orchestrator/pipeline.py` (line 32) | No code change here this phase, but verify no `portfolio` references survive |
| Modify | `.env`, `.env.example` | `PORTFOLIO_SERVICE_URL` → `CAPABILITY_SERVICE_URL` |
| Modify | `scripts/seed_demo.py` | Reorganize Akkodis seed: call new `seed_capability_profile()` helper |
| Modify | `README.md` | Update service list and port table |

---

## Tasks

### Task 1 — Branch + skeleton

**Files:**
- New branch `feat/bid-assessment` (long-lived) and `feat/bid-assessment-phase-1-capability-service` (this phase)

- [ ] **Step 1: Create branches**

```bash
git checkout master
git pull --ff-only
git checkout -b feat/bid-assessment
git push -u origin feat/bid-assessment
git checkout -b feat/bid-assessment-phase-1-capability-service
```

Expected: two new branches; second one is checked out.

- [ ] **Step 2: Verify baseline tests pass**

```bash
cd services/portfolio-service && python -m pytest -q && cd -
cd services/api-gateway && python -m pytest -q && cd -
```

Expected: both green. If not, stop and fix before starting this phase.

---

### Task 2 — Write Alembic migration 0011 (new tables only, no rename yet)

**Files:**
- Create: `migrations/versions/0011_capability_profile.py`

- [ ] **Step 1: Write the upgrade()/downgrade() migration**

Create `migrations/versions/0011_capability_profile.py`:

```python
"""Capability profile: service_lines, industries, geographies, certifications + M2Ms.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. service_lines
    op.create_table(
        "service_lines",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("parent_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("service_lines.id"), nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_service_lines_tenant_name"),
    )
    op.create_index("ix_service_lines_tenant", "service_lines", ["tenant_id"])

    # 2. industries
    op.create_table(
        "industries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_industries_tenant_name"),
    )
    op.create_index("ix_industries_tenant", "industries", ["tenant_id"])

    # 3. geographies
    op.create_table(
        "geographies",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),  # country | region | city
        sa.Column("parent_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("geographies.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("type IN ('country','region','city')",
                           name="ck_geographies_type"),
    )
    op.create_index("ix_geographies_tenant", "geographies", ["tenant_id"])

    # 4. certifications
    op.create_table(
        "certifications",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("issuing_body", sa.String, nullable=True),
        sa.Column("scope", sa.Text, nullable=True),
        sa.Column("expires_at", sa.Date, nullable=True),
        sa.Column("evidence_doc_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_certifications_tenant", "certifications", ["tenant_id"])

    # 5. service_line_industries (M2M)
    op.create_table(
        "service_line_industries",
        sa.Column("service_line_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("service_lines.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("industry_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("industries.id", ondelete="CASCADE"),
                  primary_key=True),
    )

    # 6. service_line_geographies (M2M)
    op.create_table(
        "service_line_geographies",
        sa.Column("service_line_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("service_lines.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("geography_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("geographies.id", ondelete="CASCADE"),
                  primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("service_line_geographies")
    op.drop_table("service_line_industries")
    op.drop_index("ix_certifications_tenant", table_name="certifications")
    op.drop_table("certifications")
    op.drop_index("ix_geographies_tenant", table_name="geographies")
    op.drop_table("geographies")
    op.drop_index("ix_industries_tenant", table_name="industries")
    op.drop_table("industries")
    op.drop_index("ix_service_lines_tenant", table_name="service_lines")
    op.drop_table("service_lines")
```

- [ ] **Step 2: Run migration up-and-back**

```bash
docker compose exec api-gateway alembic upgrade head
docker compose exec api-gateway alembic downgrade 0010
docker compose exec api-gateway alembic upgrade head
```

Expected: all three commands succeed; no errors about missing types or constraints.

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/0011_capability_profile.py
git commit -m "feat(db): add capability_profile tables (service_lines, industries, geographies, certifications, 2 M2Ms)"
```

---

### Task 3 — Common tenancy helper + JWT tenant_id

**Files:**
- Create: `common/common/tenancy.py`
- Modify: `services/api-gateway/auth.py` (lines 86–92 add `tenant_id`; lines 100–145 return it)

- [ ] **Step 1: Write test for tenancy helper**

Create `common/tests/test_tenancy.py`:

```python
from sqlalchemy import column, table, select

from common.tenancy import tenant_scope


def test_tenant_scope_adds_where_clause():
    t = table("docs", column("id"), column("tenant_id"))
    base = select(t.c.id)
    scoped = tenant_scope(base, "t-123", t)
    sql = str(scoped.compile(compile_kwargs={"literal_binds": True}))
    assert "tenant_id = 't-123'" in sql
```

- [ ] **Step 2: Run test (should fail — module missing)**

```bash
cd common && python -m pytest tests/test_tenancy.py -v && cd -
```

Expected: `ModuleNotFoundError: No module named 'common.tenancy'`.

- [ ] **Step 3: Implement helper**

Create `common/common/tenancy.py`:

```python
"""Tenant scoping for SQLAlchemy queries.

Code-review rule: any query touching a tenant-scoped table without this
helper is a tenancy leak.
"""
from __future__ import annotations

from typing import Any


def tenant_scope(query: Any, tenant_id: str, table: Any) -> Any:
    """Add WHERE tenant_id = :tenant_id to a query."""
    return query.where(table.c.tenant_id == tenant_id)
```

- [ ] **Step 4: Run test (should pass)**

```bash
cd common && python -m pytest tests/test_tenancy.py -v && cd -
```

Expected: PASS.

- [ ] **Step 5: Add tenant_id to JWT and `get_current_user`**

Open `services/api-gateway/auth.py`. Update `create_access_token` (around line 86) to include `tenant_id`:

```python
def create_access_token(user_id: str, role: str, company_id: str | None = None,
                         tenant_id: str | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict = {"sub": user_id, "role": role, "exp": expire}
    if company_id:
        payload["company_id"] = company_id
    if tenant_id:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
```

Update `get_current_user` to load `tenant_id` from the `users` table and include it in the returned dict (around line 123):

```python
    row = await db.execute(
        text("SELECT u.id, u.email, u.name, u.role, u.company_id, u.tenant_id, "
             "c.name AS company_name "
             "FROM users u LEFT JOIN companies c ON c.id = u.company_id WHERE u.id = :id"),
        {"id": user_id},
    )
    user = row.mappings().first()
    # ...
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "teams": teams,
        "company_id": str(user["company_id"]) if user["company_id"] else None,
        "company_name": user["company_name"],
        "tenant_id": str(user["tenant_id"]),
    }
```

Update the `login` endpoint (around line 350) to pass `tenant_id`:

```python
@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        text("SELECT id, role, password_hash, company_id, tenant_id FROM users WHERE email = :email"),
        {"email": req.email},
    )
    user = row.mappings().first()
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    company_id = str(user["company_id"]) if user["company_id"] else None
    tenant_id = str(user["tenant_id"])
    token = create_access_token(str(user["id"]), user["role"], company_id, tenant_id)
    return TokenResponse(access_token=token)
```

Update `UserResponse` (around line 66) to include `tenant_id`:

```python
class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    role: str
    teams: list[str]
    company_id: str | None = None
    company_name: str | None = None
    tenant_id: str
```

- [ ] **Step 6: Run gateway tests**

```bash
cd services/api-gateway && python -m pytest -q && cd -
```

Expected: existing tests pass (any breakage means a test fixture stubs the DB shape — fix the fixture).

- [ ] **Step 7: Commit**

```bash
git add common/common/tenancy.py common/tests/test_tenancy.py services/api-gateway/auth.py
git commit -m "feat(auth,tenancy): add tenant_id to JWT and common.tenant_scope helper"
```

---

### Task 4 — Physical rename: `portfolio-service` → `capability-service`

**Files:**
- Move: `services/portfolio-service/` → `services/capability-service/`
- Modify: `services/capability-service/pyproject.toml` — `name = "capability-service"`
- Modify: `services/capability-service/main.py` — `title="capability-service"`, log name, lifespan messages
- Modify: `services/capability-service/Dockerfile` — confirm no `portfolio` strings
- Modify: `docker-compose.yml` — service block renamed, env var renamed
- Modify: `services/api-gateway/proxy.py` — map `capabilities` instead of `products`
- Modify: `.env`, `.env.example` — `PORTFOLIO_SERVICE_URL` → `CAPABILITY_SERVICE_URL`

- [ ] **Step 1: Move the directory**

```bash
git mv services/portfolio-service services/capability-service
```

Expected: directory moved; `git status` shows renamed files.

- [ ] **Step 2: Update pyproject.toml**

In `services/capability-service/pyproject.toml`, change `name = "portfolio-service"` to `name = "capability-service"`.

- [ ] **Step 3: Update main.py title + log lines**

In `services/capability-service/main.py`:
- Line 26 `logger = get_logger("portfolio-service")` → `get_logger("capability-service")`
- Line 35 `logger.info("Starting portfolio-service")` → `"Starting capability-service"`
- Line 41 `app = FastAPI(title="portfolio-service", ...)` → `title="capability-service"`
- Line 50 `return {"status": "ok", "service": "portfolio-service"}` → `"capability-service"`

- [ ] **Step 4: Update agents.py log line**

In `services/capability-service/agents.py` line 18 `get_logger("portfolio-service.agents")` → `"capability-service.agents"`.

- [ ] **Step 5: Update Dockerfile**

`services/capability-service/Dockerfile`: replace any `portfolio-service` strings with `capability-service`. Run:

```bash
grep -n portfolio services/capability-service/Dockerfile
```

Expected: no output (none remaining).

- [ ] **Step 6: Update docker-compose.yml**

Open `docker-compose.yml`. Find the `portfolio-service:` block (around line 178). Rename the service key to `capability-service`. Update the `dockerfile:` and the volume path to the new directory:

```yaml
  capability-service:
    build:
      context: .
      dockerfile: services/capability-service/Dockerfile
    volumes:
      - ./services/capability-service:/app
      - ./common:/common
    ports:
      - "8010:8010"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
```

- [ ] **Step 7: Update gateway proxy service map**

In `services/api-gateway/proxy.py` lines 7–13 (docstring) and 27–33 (`_SERVICE_MAP`):
- Replace the docstring line `products   → portfolio-service:8010` with `capabilities → capability-service:8010`
- Replace `"products": os.environ.get("PORTFOLIO_SERVICE_URL", "http://portfolio-service:8010")` with `"capabilities": os.environ.get("CAPABILITY_SERVICE_URL", "http://capability-service:8010")`

There is no compatibility shim — `/products/*` no longer routes anywhere. The new `/capabilities/products` route (added in Task 6) supersedes it.

- [ ] **Step 8: Update env files**

Open `.env` and `.env.example`. Replace `PORTFOLIO_SERVICE_URL=...` with `CAPABILITY_SERVICE_URL=...` (same value but new variable name). Use:

```bash
sed -i 's/PORTFOLIO_SERVICE_URL/CAPABILITY_SERVICE_URL/g' .env .env.example
sed -i 's|http://portfolio-service|http://capability-service|g' .env .env.example
```

- [ ] **Step 9: Confirm no stale references**

```bash
grep -rn "portfolio-service\|PORTFOLIO_SERVICE" services/ common/ scripts/ docker-compose.yml .env .env.example 2>/dev/null
```

Expected: zero matches. If anything appears, fix it.

- [ ] **Step 10: Rebuild and smoke test**

```bash
docker compose build capability-service api-gateway
docker compose up -d capability-service api-gateway
sleep 5
curl -sf http://localhost:8010/healthz
```

Expected: `{"status":"ok","service":"capability-service"}`.

- [ ] **Step 11: Commit**

```bash
git add -A services/capability-service services/api-gateway/proxy.py docker-compose.yml .env.example
git add .env  # if any tracked .env
git commit -m "refactor: rename portfolio-service to capability-service (breaking)"
```

---

### Task 5 — Pydantic schemas for the four new dimensions

**Files:**
- Create: `services/capability-service/capabilities/__init__.py`
- Create: `services/capability-service/capabilities/schemas.py`

- [ ] **Step 1: Create package marker**

Create empty file `services/capability-service/capabilities/__init__.py`.

- [ ] **Step 2: Write schemas**

Create `services/capability-service/capabilities/schemas.py`:

```python
"""Pydantic schemas for capability profile endpoints."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


# --- service_lines ---

class ServiceLineIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    parent_id: str | None = None
    industry_ids: list[str] = Field(default_factory=list)
    geography_ids: list[str] = Field(default_factory=list)


class ServiceLineOut(BaseModel):
    id: str
    name: str
    description: str | None
    parent_id: str | None
    industry_ids: list[str]
    geography_ids: list[str]


# --- industries ---

class IndustryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class IndustryOut(BaseModel):
    id: str
    name: str


# --- geographies ---

class GeographyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: Literal["country", "region", "city"]
    parent_id: str | None = None


class GeographyOut(BaseModel):
    id: str
    name: str
    type: str
    parent_id: str | None


# --- certifications ---

class CertificationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    issuing_body: str | None = None
    scope: str | None = None
    expires_at: date | None = None
    evidence_doc_id: str | None = None


class CertificationOut(BaseModel):
    id: str
    name: str
    issuing_body: str | None
    scope: str | None
    expires_at: date | None
    evidence_doc_id: str | None
```

- [ ] **Step 3: Commit**

```bash
git add services/capability-service/capabilities/__init__.py \
        services/capability-service/capabilities/schemas.py
git commit -m "feat(capabilities): pydantic schemas for 4 dimensions"
```

---

### Task 6 — CRUD helpers + routers for the four new dimensions

**Files:**
- Create: `services/capability-service/capabilities/crud.py`
- Create: `services/capability-service/capabilities/router.py`
- Create: `services/capability-service/tests/test_crud_dimensions.py`

- [ ] **Step 1: Write a failing CRUD test**

Create `services/capability-service/tests/test_crud_dimensions.py`:

```python
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app  # noqa: E402

# Tenant header used in dev — gateway will replace with JWT-derived value
TENANT_HEADER = {"X-Tenant-Id": "11111111-1111-1111-1111-111111111111"}


@pytest.mark.asyncio
async def test_industry_crud_roundtrip():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create
        r = await ac.post("/capabilities/industries", json={"name": "Banking"}, headers=TENANT_HEADER)
        assert r.status_code == 201, r.text
        body = r.json()
        ind_id = body["id"]
        # List
        r = await ac.get("/capabilities/industries", headers=TENANT_HEADER)
        assert r.status_code == 200
        assert any(i["id"] == ind_id for i in r.json())
        # Patch
        r = await ac.patch(f"/capabilities/industries/{ind_id}",
                            json={"name": "Banking & Finance"}, headers=TENANT_HEADER)
        assert r.status_code == 200
        assert r.json()["name"] == "Banking & Finance"
        # Delete
        r = await ac.delete(f"/capabilities/industries/{ind_id}", headers=TENANT_HEADER)
        assert r.status_code == 204
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/capability-service && python -m pytest tests/test_crud_dimensions.py -v && cd -
```

Expected: FAIL — endpoint does not exist; 404 on POST.

- [ ] **Step 3: Implement CRUD helpers**

Create `services/capability-service/capabilities/crud.py`:

```python
"""DB helpers for capability dimensions. One module, one set of patterns
across all four dimensions — keep the duplication shallow so the SQL stays
readable."""
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
    # Build dynamic SET clause from non-None fields
    sets, params = [], {"id": geo_id, "t": tenant_id}
    for k, v in fields.items():
        if v is not None:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        # No-op patch: return current row
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
```

- [ ] **Step 4: Implement routers**

Create `services/capability-service/capabilities/router.py`:

```python
"""FastAPI routers mounted under /capabilities/*."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
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
```

- [ ] **Step 5: Wire routers into main.py**

Edit `services/capability-service/main.py`. Below the existing `app = FastAPI(...)` line, add:

```python
from capabilities.router import (industries_router, geographies_router,
                                   certifications_router, service_lines_router)

app.include_router(industries_router)
app.include_router(geographies_router)
app.include_router(certifications_router)
app.include_router(service_lines_router)
```

- [ ] **Step 6: Run the test (should pass)**

```bash
docker compose restart capability-service
sleep 3
cd services/capability-service && python -m pytest tests/test_crud_dimensions.py -v && cd -
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/capability-service/capabilities/ services/capability-service/main.py \
         services/capability-service/tests/test_crud_dimensions.py
git commit -m "feat(capabilities): CRUD for industries, geographies, certifications, service_lines"
```

---

### Task 7 — Profile rollup endpoint

**Files:**
- Create: `services/capability-service/capabilities/profile.py`
- Create: `services/capability-service/tests/test_profile_rollup.py`
- Modify: `services/capability-service/main.py` (include router)

- [ ] **Step 1: Failing rollup test**

Create `services/capability-service/tests/test_profile_rollup.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app  # noqa: E402

TENANT_HEADER = {"X-Tenant-Id": "11111111-1111-1111-1111-111111111111"}


@pytest.mark.asyncio
async def test_profile_rollup_returns_five_dimensions():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/capabilities/profile", headers=TENANT_HEADER)
        assert r.status_code == 200, r.text
        body = r.json()
        for key in ("service_lines", "industries", "geographies",
                     "certifications", "products"):
            assert key in body
```

- [ ] **Step 2: Run test (should fail — 404)**

```bash
cd services/capability-service && python -m pytest tests/test_profile_rollup.py -v && cd -
```

Expected: FAIL with 404.

- [ ] **Step 3: Implement profile.py**

Create `services/capability-service/capabilities/profile.py`:

```python
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
```

- [ ] **Step 4: Mount router**

In `services/capability-service/main.py`, add to the imports/inclusion block:

```python
from capabilities.profile import profile_router
app.include_router(profile_router)
```

- [ ] **Step 5: Run test (should pass)**

```bash
docker compose restart capability-service
sleep 3
cd services/capability-service && python -m pytest tests/test_profile_rollup.py -v && cd -
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/capability-service/capabilities/profile.py \
         services/capability-service/tests/test_profile_rollup.py \
         services/capability-service/main.py
git commit -m "feat(capabilities): GET /capabilities/profile rollup of 5 dimensions"
```

---

### Task 8 — Migration test + gateway smoke test

**Files:**
- Modify: `scripts/test_workflows.py` (add the new migration to the up→down→up cycle if not generic)

- [ ] **Step 1: Run reversibility check**

```bash
docker compose exec api-gateway alembic upgrade head
docker compose exec api-gateway alembic downgrade base
docker compose exec api-gateway alembic upgrade head
```

Expected: zero errors.

- [ ] **Step 2: Smoke-test gateway routing**

```bash
# Get a JWT for the seeded Akkodis admin
TOKEN=$(curl -s -X POST http://localhost:8011/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@akkodis.com","password":"changeme"}' | jq -r .access_token)

# Verify the new route works
curl -sf -H "Authorization: Bearer $TOKEN" \
     http://localhost:8011/capabilities/profile | jq '.service_lines | length'
```

Expected: a number (likely 0 until seeded).

- [ ] **Step 3: Verify legacy route is gone**

```bash
curl -s -o /dev/null -w "%{http_code}" \
     -H "Authorization: Bearer $TOKEN" \
     http://localhost:8011/products
```

Expected: `404`. (The proxy's `_SERVICE_MAP` no longer routes `products`.)

- [ ] **Step 4: Commit (if any script changes)**

```bash
git status --short scripts/
# If scripts/test_workflows.py was edited:
git add scripts/test_workflows.py
git commit -m "test: include 0011 in workflow reversibility check"
```

---

### Task 9 — Seed Akkodis capability profile

**Files:**
- Modify: `scripts/seed_demo.py` — add helper that inserts a small Akkodis capability profile

- [ ] **Step 1: Add seed helper**

Open `scripts/seed_demo.py`. Find the section that seeds products (search for `INSERT INTO products`). Below that block, add:

```python
async def seed_capability_profile(session, tenant_id: str):
    """Seed Akkodis capability profile: 3 service lines, 3 industries, 3 geographies, 2 certs."""
    import uuid
    industry_ids: dict[str, str] = {}
    for name in ("Banking", "Healthcare", "Public Sector"):
        iid = str(uuid.uuid4())
        await session.execute(
            text("INSERT INTO industries (id, tenant_id, name) "
                 "VALUES (:i, :t, :n) ON CONFLICT DO NOTHING"),
            {"i": iid, "t": tenant_id, "n": name},
        )
        industry_ids[name] = iid

    geo_ids: dict[str, str] = {}
    for name, typ in (("Canada", "country"), ("United States", "country"), ("EMEA", "region")):
        gid = str(uuid.uuid4())
        await session.execute(
            text("INSERT INTO geographies (id, tenant_id, name, type) "
                 "VALUES (:i, :t, :n, :ty) ON CONFLICT DO NOTHING"),
            {"i": gid, "t": tenant_id, "n": name, "ty": typ},
        )
        geo_ids[name] = gid

    for name, issuer in (("ISO 27001", "BSI"), ("SOC 2 Type II", "AICPA")):
        cid = str(uuid.uuid4())
        await session.execute(
            text("INSERT INTO certifications (id, tenant_id, name, issuing_body) "
                 "VALUES (:i, :t, :n, :ib) ON CONFLICT DO NOTHING"),
            {"i": cid, "t": tenant_id, "n": name, "ib": issuer},
        )

    sl_specs = [
        ("Cloud Migration", "End-to-end migration to AWS, Azure, or GCP", ["Banking", "Healthcare"], ["Canada", "United States"]),
        ("Cybersecurity Advisory", "Risk assessments, SOC 2 / ISO 27001 readiness", ["Banking", "Public Sector"], ["Canada", "EMEA"]),
        ("Data & Analytics", "Lakehouse, BI, applied ML", ["Healthcare", "Public Sector"], ["United States", "EMEA"]),
    ]
    for sl_name, sl_desc, ind_names, geo_names in sl_specs:
        sid = str(uuid.uuid4())
        await session.execute(
            text("INSERT INTO service_lines (id, tenant_id, name, description) "
                 "VALUES (:i, :t, :n, :d) ON CONFLICT DO NOTHING"),
            {"i": sid, "t": tenant_id, "n": sl_name, "d": sl_desc},
        )
        for ind_name in ind_names:
            await session.execute(
                text("INSERT INTO service_line_industries (service_line_id, industry_id) "
                     "VALUES (:s, :i) ON CONFLICT DO NOTHING"),
                {"s": sid, "i": industry_ids[ind_name]},
            )
        for geo_name in geo_names:
            await session.execute(
                text("INSERT INTO service_line_geographies (service_line_id, geography_id) "
                     "VALUES (:s, :g) ON CONFLICT DO NOTHING"),
                {"s": sid, "g": geo_ids[geo_name]},
            )
    await session.commit()
```

Call `await seed_capability_profile(session, AKKODIS_TENANT_ID)` from the script's main coroutine (search the file for the existing `await seed_products(...)` or similar and add immediately after — preserving order: tenants first, capabilities next, then products/documents/RFPs).

If `AKKODIS_TENANT_ID` is not yet a top-level constant in the script, derive it via:

```python
row = await session.execute(text("SELECT id::text FROM tenants WHERE slug = 'akkodis'"))
AKKODIS_TENANT_ID = row.scalar_one()
```

- [ ] **Step 2: Run seed**

```bash
docker compose exec api-gateway python /scripts/seed_demo.py
```

Expected: no errors. Re-running is idempotent (every INSERT uses `ON CONFLICT DO NOTHING`).

- [ ] **Step 3: Verify**

```bash
curl -sf -H "Authorization: Bearer $TOKEN" \
     http://localhost:8011/capabilities/profile | \
     jq '{service_lines: .service_lines | length, industries: .industries | length, geographies: .geographies | length, certifications: .certifications | length}'
```

Expected: `{service_lines: 3, industries: 3, geographies: 3, certifications: 2}`.

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_demo.py
git commit -m "feat(seed): seed Akkodis 5-dim capability profile"
```

---

### Task 10 — Documentation + phase close

**Files:**
- Modify: `README.md` — service list and port table
- Modify: `docs/superpowers/plans/2026-05-13-bid-assessment/README.md` — mark phase 1 as complete

- [ ] **Step 1: Update README service list**

In `README.md`, find the service listing (search for `portfolio-service`). Replace `portfolio-service` with `capability-service` everywhere it appears, and add a short note in the "Services" section:

> `capability-service` (port 8010) — manages the 5-dimension tenant capability profile (service lines, industries, geographies, certifications, products) and serves `/capabilities/*`.

- [ ] **Step 2: Update phase status**

In `docs/superpowers/plans/2026-05-13-bid-assessment/README.md`, mark phase 1 as complete (replace the table row description with "✓ Done — <date>").

- [ ] **Step 3: Merge phase branch into the long-lived branch**

```bash
git checkout feat/bid-assessment
git merge --no-ff feat/bid-assessment-phase-1-capability-service \
  -m "Phase 1: capability-service rename + 5-dim profile"
git push origin feat/bid-assessment
```

- [ ] **Step 4: Demo affordance check**

Confirm via the seeded demo:

```bash
# All five dimensions return non-empty for Akkodis
TOKEN=$(curl -s -X POST http://localhost:8011/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@akkodis.com","password":"changeme"}' | jq -r .access_token)
curl -sf -H "Authorization: Bearer $TOKEN" \
     http://localhost:8011/capabilities/profile | jq 'keys'
```

Expected: `["certifications","geographies","industries","products","service_lines"]`.

Phase 1 done.
