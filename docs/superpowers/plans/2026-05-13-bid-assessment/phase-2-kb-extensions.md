# Phase 2 — Knowledge Base Extensions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this phase task-by-task.

**Goal:** Add the `documents.category` enum, the typed `past_proposals` and `contracts` entity tables (hybrid KB), the snippet library façade, category-weighted RRF in retrieval, and tag classification in the ExtractionAgent. Sets up everything the bid-assessment pipeline (phase 3) needs to read from.

**Architecture:** Two Alembic migrations (`0012_documents_category.py`, `0013_typed_entities.py`). `content-service` gains a snippet-aware chunker branch and two new endpoint groups. `retrieval-service` adds category and tag boosts to its RRF score formula. Existing `ExtractionAgent` (in `services/content-service/agents.py`) emits a `tags[]` array per requirement, classified against the union of snippet topic-tags for the tenant.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x async, Alembic, pgvector. Frontend touches deferred to phase 4.

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `migrations/versions/0012_documents_category.py` | `documents.category` column + CHECK + index |
| Create | `migrations/versions/0013_typed_entities.py` | `past_proposals`, `contracts` tables |
| Modify | `services/content-service/chunker.py` | Single-chunk branch for `boilerplate_snippet` |
| Modify | `services/content-service/ingestion.py` | Accept `category` + per-category metadata on upload |
| Create | `services/content-service/snippets.py` | `/snippets` CRUD façade |
| Create | `services/content-service/typed_entities.py` | `/past-proposals` + `/contracts` endpoints |
| Modify | `services/content-service/main.py` | Mount new routers |
| Create | `services/content-service/tests/test_snippets.py` | Snippet lifecycle test |
| Create | `services/content-service/tests/test_typed_entities.py` | Past-proposal + contract round-trip |
| Modify | `services/retrieval-service/retrieve.py` | Add `category_boosts` + `topic_tag_boost` to RRF score |
| Modify | `services/retrieval-service/tests/test_retrieve.py` | Verify boost arithmetic |
| Modify | `services/content-service/agents.py` (ExtractionAgent) | Emit `tags[]` per requirement |
| Modify | `services/api-gateway/proxy.py` | Add `snippets`, `past-proposals`, `contracts` route keys |
| Modify | `scripts/seed_demo.py` | Seed 3 snippets, 1 won past-proposal, 1 contract for Akkodis |

---

## Tasks

### Task 1 — Branch + reset

- [ ] **Step 1: New phase branch off the long-lived branch**

```bash
git checkout feat/bid-assessment
git pull --ff-only
git checkout -b feat/bid-assessment-phase-2-kb-extensions
```

- [ ] **Step 2: Baseline tests green**

```bash
cd services/content-service && python -m pytest -q && cd -
cd services/retrieval-service && python -m pytest -q && cd -
```

Expected: both green.

---

### Task 2 — Migration 0012: documents.category

**Files:**
- Create: `migrations/versions/0012_documents_category.py`

- [ ] **Step 1: Write migration**

```python
"""documents.category column + CHECK + index.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIES = ("general", "product_doc", "past_proposal", "contract", "boilerplate_snippet")


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("category", sa.String, nullable=False, server_default="general"),
    )
    op.create_check_constraint(
        "ck_documents_category",
        "documents",
        f"category IN {CATEGORIES}",
    )
    op.create_index(
        "ix_documents_tenant_category",
        "documents",
        ["tenant_id", "category"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_tenant_category", table_name="documents")
    op.drop_constraint("ck_documents_category", "documents", type_="check")
    op.drop_column("documents", "category")
```

- [ ] **Step 2: Run reversibility**

```bash
docker compose exec api-gateway alembic upgrade head
docker compose exec api-gateway alembic downgrade 0011
docker compose exec api-gateway alembic upgrade head
```

Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/0012_documents_category.py
git commit -m "feat(db): add documents.category enum + index"
```

---

### Task 3 — Migration 0013: typed entity tables

**Files:**
- Create: `migrations/versions/0013_typed_entities.py`

- [ ] **Step 1: Write migration**

```python
"""past_proposals and contracts typed entity tables.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "past_proposals",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("client_name", sa.String, nullable=True),
        sa.Column("industry_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("industries.id"), nullable=True),
        sa.Column("submitted_at", sa.Date, nullable=False),
        sa.Column("outcome", sa.String, nullable=False, server_default="pending"),
        sa.Column("outcome_reason", sa.Text, nullable=True),
        sa.Column("value_amount", sa.Numeric, nullable=True),
        sa.Column("value_currency", sa.CHAR(3), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("outcome IN ('won','lost','withdrawn','pending')",
                           name="ck_past_proposals_outcome"),
    )
    op.create_index("ix_past_proposals_tenant_outcome",
                    "past_proposals", ["tenant_id", "outcome"])

    op.create_table(
        "contracts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("client_name", sa.String, nullable=False),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("expires_at", sa.Date, nullable=True),
        sa.Column("value_amount", sa.Numeric, nullable=True),
        sa.Column("value_currency", sa.CHAR(3), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contracts_tenant_expires",
                    "contracts", ["tenant_id", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_contracts_tenant_expires", table_name="contracts")
    op.drop_table("contracts")
    op.drop_index("ix_past_proposals_tenant_outcome", table_name="past_proposals")
    op.drop_table("past_proposals")
```

- [ ] **Step 2: Run reversibility**

```bash
docker compose exec api-gateway alembic upgrade head
docker compose exec api-gateway alembic downgrade 0012
docker compose exec api-gateway alembic upgrade head
```

Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/0013_typed_entities.py
git commit -m "feat(db): add past_proposals + contracts typed entity tables"
```

---

### Task 4 — Snippet-aware chunker

**Files:**
- Modify: `services/content-service/chunker.py`

- [ ] **Step 1: Write a failing chunker test**

Append to `services/content-service/tests/test_chunker.py` (create if missing):

```python
import pytest

from chunker import chunk_document


def test_snippet_category_produces_single_chunk():
    text = "This is a 2-paragraph snippet.\n\nIt should not be split."
    chunks = chunk_document(text=text, category="boilerplate_snippet")
    assert len(chunks) == 1
    assert chunks[0]["text"] == text
    assert chunks[0]["position"] == 0


def test_general_category_splits_long_text():
    long_text = ("paragraph one. " * 100) + "\n\n" + ("paragraph two. " * 100)
    chunks = chunk_document(text=long_text, category="general")
    assert len(chunks) > 1
```

- [ ] **Step 2: Run test (should fail — `category` kwarg unknown)**

```bash
cd services/content-service && python -m pytest tests/test_chunker.py -v && cd -
```

Expected: FAIL.

- [ ] **Step 3: Add `category` parameter to chunker**

Open `services/content-service/chunker.py`. Whatever the current signature of `chunk_document` is (find it via `grep -n 'def chunk_document' services/content-service/chunker.py`), add a `category: str = "general"` kwarg. At the top of the function body add:

```python
if category == "boilerplate_snippet":
    return [{"text": text, "position": 0, "metadata": {}}]
```

(adjust the return shape to match whatever the rest of `chunker.py` returns — e.g., if it returns a list of `Chunk` dataclass instances, return `[Chunk(text=text, position=0, metadata={})]` instead.)

- [ ] **Step 4: Run test (should pass)**

```bash
cd services/content-service && python -m pytest tests/test_chunker.py -v && cd -
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/content-service/chunker.py services/content-service/tests/test_chunker.py
git commit -m "feat(content): single-chunk path for boilerplate_snippet category"
```

---

### Task 5 — Ingestion accepts `category` and per-category metadata

**Files:**
- Modify: `services/content-service/ingestion.py`
- Modify: `services/content-service/schemas.py`

- [ ] **Step 1: Add category to upload schema**

In `services/content-service/schemas.py`, find the upload request model (likely `UploadRequest` or `DocumentCreate`). Add:

```python
from typing import Literal

class UploadRequest(BaseModel):  # or whatever the existing class is named
    # ... existing fields ...
    category: Literal[
        "general", "product_doc", "past_proposal",
        "contract", "boilerplate_snippet"
    ] = "general"
    metadata: dict = Field(default_factory=dict)
```

- [ ] **Step 2: Persist category on upload**

In `services/content-service/ingestion.py`, find the `INSERT INTO documents (...)` SQL. Add `category` to the column list and parameter binding. Pass `category=req.category` through from the handler.

- [ ] **Step 3: Pass category to chunker**

In the same `ingestion.py`, wherever `chunk_document(...)` is called, pass `category=req.category`.

- [ ] **Step 4: Run service tests**

```bash
docker compose restart content-service
sleep 3
cd services/content-service && python -m pytest -q && cd -
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add services/content-service/ingestion.py services/content-service/schemas.py
git commit -m "feat(content): accept category on upload; route into chunker"
```

---

### Task 6 — Snippet façade

**Files:**
- Create: `services/content-service/snippets.py`
- Create: `services/content-service/tests/test_snippets.py`
- Modify: `services/content-service/main.py`

- [ ] **Step 1: Failing test**

Create `services/content-service/tests/test_snippets.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app  # noqa: E402

TENANT_HEADER = {
    "X-Tenant-Id": "11111111-1111-1111-1111-111111111111",
    "X-User-Role": "content_admin",
    "X-User-Id": "22222222-2222-2222-2222-222222222222",
}


@pytest.mark.asyncio
async def test_snippet_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create (content_admin → auto-approved)
        r = await ac.post("/snippets",
                           json={"title": "GDPR posture", "body": "We comply with GDPR...",
                                  "topic_tags": ["gdpr", "privacy"]},
                           headers=TENANT_HEADER)
        assert r.status_code == 201, r.text
        snippet_id = r.json()["id"]
        assert r.json()["status"] == "approved"
        # List
        r = await ac.get("/snippets?topic=gdpr", headers=TENANT_HEADER)
        assert r.status_code == 200
        assert any(s["id"] == snippet_id for s in r.json())
        # Patch (bumps version, resets to pending_approval)
        r = await ac.patch(f"/snippets/{snippet_id}",
                            json={"title": "GDPR posture", "body": "Updated body",
                                   "topic_tags": ["gdpr"]},
                            headers=TENANT_HEADER)
        assert r.status_code == 200
        assert r.json()["metadata"]["version"] == 2
        # Soft delete
        r = await ac.delete(f"/snippets/{snippet_id}", headers=TENANT_HEADER)
        assert r.status_code == 204
```

- [ ] **Step 2: Run test (should fail — endpoint missing)**

```bash
cd services/content-service && python -m pytest tests/test_snippets.py -v && cd -
```

Expected: FAIL — 404.

- [ ] **Step 3: Implement snippets.py**

Create `services/content-service/snippets.py`:

```python
"""Snippet library — façade over documents with category='boilerplate_snippet'."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db
from common.embedder import SentenceTransformerEmbedder

router = APIRouter(prefix="/snippets", tags=["snippets"])
_embedder = SentenceTransformerEmbedder()


class SnippetIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    topic_tags: list[str] = Field(default_factory=list)


def _ctx(x_tenant_id: str | None = Header(default=None),
         x_user_id: str | None = Header(default=None),
         x_user_role: str | None = Header(default=None)) -> dict:
    if not x_tenant_id:
        raise HTTPException(401, "X-Tenant-Id header required")
    return {"tenant_id": x_tenant_id, "user_id": x_user_id or "",
            "role": x_user_role or "end_user"}


@router.post("", status_code=201)
async def create_snippet(req: SnippetIn,
                          ctx: dict = Depends(_ctx),
                          db: AsyncSession = Depends(get_db)):
    doc_id = str(uuid.uuid4())
    auto_approve = ctx["role"] in ("content_admin", "system_admin")
    approval_status = "approved" if auto_approve else "pending_approval"
    metadata = {
        "topic_tags": req.topic_tags,
        "version": 1,
        "approved_by": ctx["user_id"] if auto_approve else None,
    }
    await db.execute(
        text("INSERT INTO documents (id, tenant_id, title, content, category, "
             "metadata, status) VALUES (:id, :t, :ti, :c, 'boilerplate_snippet', "
             ":m::jsonb, :s)"),
        {"id": doc_id, "t": ctx["tenant_id"], "ti": req.title, "c": req.body,
         "m": json.dumps(metadata), "s": approval_status},
    )
    # Single-chunk insert + embedding
    emb = _embedder.embed([req.body])[0]
    await db.execute(
        text("INSERT INTO chunks (id, document_id, position, text, embedding) "
             "VALUES (gen_random_uuid(), :did, 0, :t, :e)"),
        {"did": doc_id, "t": req.body, "e": emb},
    )
    await db.commit()
    return {"id": doc_id, "title": req.title, "body": req.body,
            "metadata": metadata, "status": approval_status}


@router.get("")
async def list_snippets(topic: str | None = None, q: str | None = None,
                          ctx: dict = Depends(_ctx),
                          db: AsyncSession = Depends(get_db)):
    sql = ("SELECT id::text AS id, title, content AS body, metadata, status "
           "FROM documents WHERE tenant_id = :t AND category = 'boilerplate_snippet' "
           "AND status != 'archived'")
    params: dict = {"t": ctx["tenant_id"]}
    if topic:
        sql += " AND metadata->'topic_tags' ? :tg"
        params["tg"] = topic
    if q:
        sql += " AND (title ILIKE :q OR content ILIKE :q)"
        params["q"] = f"%{q}%"
    sql += " ORDER BY title LIMIT 100"
    rows = await db.execute(text(sql), params)
    return [dict(r) for r in rows.mappings().all()]


@router.patch("/{snippet_id}")
async def patch_snippet(snippet_id: str, req: SnippetIn,
                         ctx: dict = Depends(_ctx),
                         db: AsyncSession = Depends(get_db)):
    if ctx["role"] not in ("content_admin", "system_admin"):
        raise HTTPException(403, "Forbidden")
    row = await db.execute(
        text("SELECT metadata FROM documents WHERE id = :id AND tenant_id = :t "
             "AND category = 'boilerplate_snippet'"),
        {"id": snippet_id, "t": ctx["tenant_id"]},
    )
    existing = row.mappings().first()
    if not existing:
        raise HTTPException(404, "Not found")
    md = dict(existing["metadata"])
    md["version"] = int(md.get("version", 1)) + 1
    md["topic_tags"] = req.topic_tags
    await db.execute(
        text("UPDATE documents SET title = :ti, content = :c, metadata = :m::jsonb, "
             "status = 'pending_approval' WHERE id = :id"),
        {"ti": req.title, "c": req.body, "m": json.dumps(md), "id": snippet_id},
    )
    # Re-embed the single chunk
    emb = _embedder.embed([req.body])[0]
    await db.execute(
        text("UPDATE chunks SET text = :t, embedding = :e WHERE document_id = :did"),
        {"t": req.body, "e": emb, "did": snippet_id},
    )
    await db.commit()
    return {"id": snippet_id, "title": req.title, "body": req.body,
            "metadata": md, "status": "pending_approval"}


@router.delete("/{snippet_id}", status_code=204)
async def delete_snippet(snippet_id: str,
                          ctx: dict = Depends(_ctx),
                          db: AsyncSession = Depends(get_db)):
    if ctx["role"] not in ("content_admin", "system_admin"):
        raise HTTPException(403, "Forbidden")
    r = await db.execute(
        text("UPDATE documents SET status = 'archived' WHERE id = :id AND tenant_id = :t "
             "AND category = 'boilerplate_snippet'"),
        {"id": snippet_id, "t": ctx["tenant_id"]},
    )
    if (r.rowcount or 0) == 0:
        raise HTTPException(404, "Not found")
    await db.commit()
```

- [ ] **Step 4: Mount router**

In `services/content-service/main.py`, add near the bottom (or wherever routers are included):

```python
from snippets import router as snippets_router
app.include_router(snippets_router)
```

- [ ] **Step 5: Run test (should pass)**

```bash
docker compose restart content-service
sleep 3
cd services/content-service && python -m pytest tests/test_snippets.py -v && cd -
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/content-service/snippets.py \
         services/content-service/tests/test_snippets.py \
         services/content-service/main.py
git commit -m "feat(snippets): CRUD façade over documents.boilerplate_snippet"
```

---

### Task 7 — Typed-entity endpoints (past-proposals, contracts)

**Files:**
- Create: `services/content-service/typed_entities.py`
- Create: `services/content-service/tests/test_typed_entities.py`
- Modify: `services/content-service/main.py`

- [ ] **Step 1: Failing test**

Create `services/content-service/tests/test_typed_entities.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app  # noqa: E402

TENANT_HEADER = {
    "X-Tenant-Id": "11111111-1111-1111-1111-111111111111",
    "X-User-Role": "content_admin",
    "X-User-Id": "22222222-2222-2222-2222-222222222222",
}


@pytest.mark.asyncio
async def test_past_proposal_create_and_set_outcome():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # We rely on a pre-seeded document id; this test will work after seed runs.
        r = await ac.post("/past-proposals", json={
            "title": "FOO Bank — 2023 modernization proposal",
            "body": "We propose a phased cloud migration ...",
            "client_name": "FOO Bank",
            "submitted_at": "2023-04-15",
            "outcome": "pending",
        }, headers=TENANT_HEADER)
        assert r.status_code == 201, r.text
        pp_id = r.json()["id"]
        # Set outcome
        r = await ac.patch(f"/past-proposals/{pp_id}",
                            json={"outcome": "won", "outcome_reason": "Best price"},
                            headers=TENANT_HEADER)
        assert r.status_code == 200
        assert r.json()["outcome"] == "won"
        # Filter list
        r = await ac.get("/past-proposals?outcome=won", headers=TENANT_HEADER)
        assert r.status_code == 200
        assert any(p["id"] == pp_id for p in r.json())


@pytest.mark.asyncio
async def test_contract_create():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/contracts", json={
            "title": "FOO Bank — MSA 2023",
            "body": "Master Services Agreement ...",
            "client_name": "FOO Bank",
            "effective_date": "2023-06-01",
            "expires_at": "2026-05-31",
        }, headers=TENANT_HEADER)
        assert r.status_code == 201, r.text
```

- [ ] **Step 2: Run test (should fail)**

```bash
cd services/content-service && python -m pytest tests/test_typed_entities.py -v && cd -
```

Expected: FAIL — 404.

- [ ] **Step 3: Implement typed-entity endpoints**

Create `services/content-service/typed_entities.py`:

```python
"""POST/PATCH/GET /past-proposals and /contracts.

Each POST creates both a documents row (for retrieval) and a typed row.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db
from common.embedder import SentenceTransformerEmbedder

_embedder = SentenceTransformerEmbedder()

past_router = APIRouter(prefix="/past-proposals", tags=["past_proposals"])
contracts_router = APIRouter(prefix="/contracts", tags=["contracts"])


# --- helpers ---

def _ctx(x_tenant_id: str | None = Header(default=None),
         x_user_role: str | None = Header(default=None)) -> dict:
    if not x_tenant_id:
        raise HTTPException(401, "X-Tenant-Id header required")
    return {"tenant_id": x_tenant_id, "role": x_user_role or "end_user"}


async def _create_document(db: AsyncSession, tenant_id: str, title: str, body: str,
                            category: str, metadata: dict) -> str:
    doc_id = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO documents (id, tenant_id, title, content, category, metadata, status) "
             "VALUES (:id, :t, :ti, :c, :cat, :m::jsonb, 'approved')"),
        {"id": doc_id, "t": tenant_id, "ti": title, "c": body,
         "cat": category, "m": json.dumps(metadata)},
    )
    # Embed once as a single chunk; phase-2 keeps this simple for non-snippet
    # categories too. Full chunker remains for /documents endpoint.
    emb = _embedder.embed([body])[0]
    await db.execute(
        text("INSERT INTO chunks (id, document_id, position, text, embedding) "
             "VALUES (gen_random_uuid(), :d, 0, :t, :e)"),
        {"d": doc_id, "t": body, "e": emb},
    )
    return doc_id


# --- past_proposals ---

class PastProposalIn(BaseModel):
    title: str
    body: str
    client_name: str | None = None
    industry_id: str | None = None
    submitted_at: date
    outcome: str = "pending"  # won|lost|withdrawn|pending
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
           "WHERE id = :id AND tenant_id = :t RETURNING id::text AS id, outcome, outcome_reason")
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
```

- [ ] **Step 4: Mount routers**

In `services/content-service/main.py`:

```python
from typed_entities import past_router, contracts_router
app.include_router(past_router)
app.include_router(contracts_router)
```

- [ ] **Step 5: Run test (should pass)**

```bash
docker compose restart content-service
sleep 3
cd services/content-service && python -m pytest tests/test_typed_entities.py -v && cd -
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/content-service/typed_entities.py \
         services/content-service/tests/test_typed_entities.py \
         services/content-service/main.py
git commit -m "feat(content): /past-proposals and /contracts endpoints"
```

---

### Task 8 — Add new route keys to gateway proxy

**Files:**
- Modify: `services/api-gateway/proxy.py`

- [ ] **Step 1: Extend `_SERVICE_MAP`**

In `services/api-gateway/proxy.py`, in `_SERVICE_MAP` add:

```python
    "snippets": os.environ.get("CONTENT_SERVICE_URL", "http://content-service:8003"),
    "past-proposals": os.environ.get("CONTENT_SERVICE_URL", "http://content-service:8003"),
    "contracts": os.environ.get("CONTENT_SERVICE_URL", "http://content-service:8003"),
```

The docstring (lines 7–13) should mention the new routes for clarity.

- [ ] **Step 2: Smoke test**

```bash
docker compose restart api-gateway
sleep 3
TOKEN=$(curl -s -X POST http://localhost:8011/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@akkodis.com","password":"changeme"}' | jq -r .access_token)
curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8011/snippets | jq .
curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8011/past-proposals | jq .
curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8011/contracts | jq .
```

Expected: each returns `[]` (empty arrays until seeded).

- [ ] **Step 3: Commit**

```bash
git add services/api-gateway/proxy.py
git commit -m "feat(gateway): route snippets, past-proposals, contracts to content-service"
```

---

### Task 9 — Category-weighted RRF in retrieval-service

**Files:**
- Modify: `services/retrieval-service/retrieve.py`
- Modify: `services/retrieval-service/tests/test_retrieve.py`

- [ ] **Step 1: Failing test**

Append to `services/retrieval-service/tests/test_retrieve.py`:

```python
import pytest

from retrieve import apply_category_boost


def test_snippet_gets_largest_boost():
    rrf = 0.01
    boosts = {"boilerplate_snippet": 0.15, "general": 0.0,
               "past_proposal_won": 0.10, "past_proposal_lost": 0.02,
               "contract": 0.05}
    snippet_score = apply_category_boost(rrf, "boilerplate_snippet", "won", boosts)
    general_score = apply_category_boost(rrf, "general", None, boosts)
    won_score = apply_category_boost(rrf, "past_proposal", "won", boosts)
    lost_score = apply_category_boost(rrf, "past_proposal", "lost", boosts)
    assert snippet_score > won_score > lost_score > general_score
```

- [ ] **Step 2: Run test (should fail — function missing)**

```bash
cd services/retrieval-service && python -m pytest tests/test_retrieve.py -v && cd -
```

Expected: FAIL — `ImportError` or `AttributeError`.

- [ ] **Step 3: Implement `apply_category_boost`**

Open `services/retrieval-service/retrieve.py`. Add:

```python
def apply_category_boost(rrf_score: float, category: str | None,
                          outcome: str | None,
                          boosts: dict[str, float]) -> float:
    """Add a category boost to an RRF score. past_proposal splits into
    won/lost variants via the chunk's metadata.outcome."""
    if category == "past_proposal":
        key = "past_proposal_won" if outcome == "won" else (
              "past_proposal_lost" if outcome == "lost" else "general")
    elif category in ("boilerplate_snippet", "contract", "product_doc", "general"):
        key = category
    else:
        key = "general"
    return rrf_score + boosts.get(key, 0.0)
```

In the main `retrieve()` function, after computing each chunk's RRF score, apply the boost. Find the line where the chunk's final score is set and replace it with:

```python
# Pull category from the document join + outcome from chunk.metadata (past_proposal only)
category = chunk_row.get("category", "general")
outcome = (chunk_row.get("metadata") or {}).get("outcome")
boosts = req.score_adjustments.get("category_boosts") or _DEFAULT_CATEGORY_BOOSTS
chunk_row["score"] = apply_category_boost(rrf, category, outcome, boosts)
```

Add at module top:

```python
_DEFAULT_CATEGORY_BOOSTS = {
    "boilerplate_snippet": 0.15,
    "past_proposal_won":   0.10,
    "past_proposal_lost":  0.02,
    "contract":            0.05,
    "product_doc":         0.00,
    "general":             0.00,
}
```

Note: the SQL that joins `chunks` → `documents` must SELECT `documents.category`. Update the SELECT clause accordingly.

- [ ] **Step 4: Run test (should pass)**

```bash
cd services/retrieval-service && python -m pytest tests/test_retrieve.py -v && cd -
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/retrieval-service/retrieve.py services/retrieval-service/tests/test_retrieve.py
git commit -m "feat(retrieval): category-weighted RRF (snippets, past_proposal_won/lost, contracts)"
```

---

### Task 10 — Tag classification in ExtractionAgent

**Files:**
- Modify: `services/content-service/agents.py`

- [ ] **Step 1: Failing test**

Create `services/content-service/tests/test_tag_classification.py`:

```python
import pytest

from agents import ExtractionAgent  # adjust import to match actual class name


@pytest.mark.asyncio
async def test_requirements_get_tags_from_snippet_vocab(monkeypatch):
    # Monkey-patch the snippet-vocab fetcher to return a fixed list
    vocab = ["gdpr", "soc2", "sla"]
    async def fake_vocab(db, tenant_id): return vocab
    from agents import _load_snippet_tag_vocab
    monkeypatch.setattr("agents._load_snippet_tag_vocab", fake_vocab)

    agent = ExtractionAgent()
    out = await agent.run_with_vocab(
        rfp_text="Vendor must demonstrate GDPR compliance and SOC 2 attestation.",
        tenant_id="t-1", db=None, vocab=vocab,
    )
    tags_for_first = out[0]["tags"]
    assert "gdpr" in tags_for_first
    assert "soc2" in tags_for_first
```

- [ ] **Step 2: Find the existing extraction logic**

```bash
grep -n "class.*Extract\|def.*extract" services/content-service/agents.py | head
```

The class might be `RequirementExtractionAgent` or similar.

- [ ] **Step 3: Add `_load_snippet_tag_vocab` + integrate into extraction**

Add at module level in `services/content-service/agents.py`:

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _load_snippet_tag_vocab(db: AsyncSession, tenant_id: str) -> list[str]:
    """Union of all `metadata.topic_tags` values across approved snippets."""
    rows = await db.execute(
        text("SELECT metadata->'topic_tags' AS tags FROM documents "
             "WHERE tenant_id = :t AND category = 'boilerplate_snippet' "
             "AND status = 'approved'"),
        {"t": tenant_id},
    )
    vocab: set[str] = set()
    for r in rows.mappings().all():
        tags = r["tags"] or []
        if isinstance(tags, list):
            vocab.update(str(t) for t in tags)
    return sorted(vocab)


def _classify_tags(requirement_text: str, vocab: list[str]) -> list[str]:
    """Simple keyword match. The LLM-driven variant is a phase-2 backlog item."""
    lc = requirement_text.lower()
    return [tag for tag in vocab if tag.lower() in lc]
```

In the existing extraction agent, after producing the list of requirement dicts, decorate each:

```python
vocab = await _load_snippet_tag_vocab(db, tenant_id)
for req in requirements:
    req["tags"] = _classify_tags(req["text"], vocab)
```

Also add a thin convenience method `async def run_with_vocab(self, rfp_text, tenant_id, db, vocab)` that bypasses the DB fetch — used by the test above.

- [ ] **Step 4: Run test (should pass)**

```bash
cd services/content-service && python -m pytest tests/test_tag_classification.py -v && cd -
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/content-service/agents.py services/content-service/tests/test_tag_classification.py
git commit -m "feat(extraction): emit tags[] per requirement from snippet vocab"
```

---

### Task 11 — Seed Akkodis snippets, one won past-proposal, one contract

**Files:**
- Modify: `scripts/seed_demo.py`

- [ ] **Step 1: Add seed snippets**

Append to `scripts/seed_demo.py` (or insert near the existing document-seeding block). Wrap in an `async def seed_snippets(session, tenant_id)`:

```python
async def seed_snippets(session, tenant_id: str):
    snippets = [
        ("GDPR posture",
         "Akkodis processes personal data per Art. 6/9 GDPR. We sign DPAs with controllers, "
         "honour DSARs within 30 days, and maintain breach-notification procedures.",
         ["gdpr", "privacy"]),
        ("SOC 2 Type II",
         "We hold an active SOC 2 Type II report covering security and availability "
         "trust services criteria; report furnished on NDA.",
         ["soc2", "security"]),
        ("Default SLA (gold tier)",
         "99.95% availability, P1 response 30 min, RTO 4 h, RPO 1 h. Monthly reporting.",
         ["sla"]),
    ]
    for title, body, tags in snippets:
        # Look up if already seeded by title to keep idempotent
        existing = await session.execute(
            text("SELECT id FROM documents WHERE tenant_id = :t AND title = :ti "
                 "AND category = 'boilerplate_snippet'"),
            {"t": tenant_id, "ti": title},
        )
        if existing.first():
            continue
        await session.execute(
            text("INSERT INTO documents (id, tenant_id, title, content, category, "
                 "metadata, status) VALUES (gen_random_uuid(), :t, :ti, :c, "
                 "'boilerplate_snippet', :m::jsonb, 'approved')"),
            {"t": tenant_id, "ti": title, "c": body,
             "m": json.dumps({"topic_tags": tags, "version": 1, "approved_by": None})},
        )
    await session.commit()
```

Add similar `seed_past_proposals(...)` and `seed_contracts(...)` helpers that each insert one example record. Call all three after `seed_capability_profile(...)` in the main coroutine.

- [ ] **Step 2: Run seed**

```bash
docker compose exec api-gateway python /scripts/seed_demo.py
```

Expected: no errors. Re-runs are idempotent.

- [ ] **Step 3: Verify**

```bash
curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8011/snippets | jq 'length'
curl -sf -H "Authorization: Bearer $TOKEN" \
     "http://localhost:8011/past-proposals?outcome=won" | jq 'length'
curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8011/contracts | jq 'length'
```

Expected: `3`, `1`, `1`.

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_demo.py
git commit -m "feat(seed): 3 snippets, 1 won past-proposal, 1 contract for Akkodis"
```

---

### Task 12 — Merge phase 2

- [ ] **Step 1: All service tests green**

```bash
for svc in content-service retrieval-service api-gateway; do
  echo "--- $svc ---"
  (cd services/$svc && python -m pytest -q)
done
```

Expected: green across the board.

- [ ] **Step 2: Migration reversibility**

```bash
docker compose exec api-gateway alembic upgrade head
docker compose exec api-gateway alembic downgrade 0010
docker compose exec api-gateway alembic upgrade head
```

Expected: zero errors.

- [ ] **Step 3: Merge into long-lived branch**

```bash
git checkout feat/bid-assessment
git merge --no-ff feat/bid-assessment-phase-2-kb-extensions \
  -m "Phase 2: KB extensions (category, typed entities, snippets, RRF boosts, tag classify)"
git push origin feat/bid-assessment
```

Phase 2 done.
