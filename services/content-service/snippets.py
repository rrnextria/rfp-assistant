"""Snippet library — façade over documents with category='boilerplate_snippet'.

A snippet is physically a documents row whose body lives in `content` and
whose `metadata.topic_tags` defines what compliance items it can answer.
Snippets get one chunk (no splitting) so retrieval returns the whole text.
"""
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


def _emb_to_vector(emb: list[float]) -> str:
    return "[" + ",".join(str(v) for v in emb) + "]"


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
        "approved": auto_approve,
    }
    await db.execute(
        text("INSERT INTO documents (id, tenant_id, title, category, status) "
             "VALUES (:id, :t, :ti, 'boilerplate_snippet', :s)"),
        {"id": doc_id, "t": ctx["tenant_id"], "ti": req.title, "s": approval_status},
    )
    # Single-chunk insert with embedding
    emb = _embedder.embed([req.body])[0]
    await db.execute(
        text("INSERT INTO chunks (id, document_id, text, metadata, embedding) "
             "VALUES (gen_random_uuid(), :did, :t, CAST(:m AS jsonb), CAST(:e AS vector))"),
        {"did": doc_id, "t": req.body, "m": json.dumps(metadata),
         "e": _emb_to_vector(emb)},
    )
    await db.commit()
    return {"id": doc_id, "title": req.title, "body": req.body,
            "metadata": metadata, "status": approval_status}


@router.get("")
async def list_snippets(topic: str | None = None, q: str | None = None,
                          ctx: dict = Depends(_ctx),
                          db: AsyncSession = Depends(get_db)):
    sql = ("SELECT d.id::text AS id, d.title, c.text AS body, c.metadata, d.status "
           "FROM documents d "
           "LEFT JOIN chunks c ON c.document_id = d.id "
           "WHERE d.tenant_id = :t AND d.category = 'boilerplate_snippet' "
           "AND d.status != 'archived'")
    params: dict = {"t": ctx["tenant_id"]}
    if topic:
        sql += " AND c.metadata->'topic_tags' ? :tg"
        params["tg"] = topic
    if q:
        sql += " AND (d.title ILIKE :q OR c.text ILIKE :q)"
        params["q"] = f"%{q}%"
    sql += " ORDER BY d.title LIMIT 100"
    rows = await db.execute(text(sql), params)
    return [dict(r) for r in rows.mappings().all()]


@router.patch("/{snippet_id}")
async def patch_snippet(snippet_id: str, req: SnippetIn,
                         ctx: dict = Depends(_ctx),
                         db: AsyncSession = Depends(get_db)):
    if ctx["role"] not in ("content_admin", "system_admin"):
        raise HTTPException(403, "Forbidden")
    row = await db.execute(
        text("SELECT c.metadata FROM documents d "
             "LEFT JOIN chunks c ON c.document_id = d.id "
             "WHERE d.id = :id AND d.tenant_id = :t "
             "AND d.category = 'boilerplate_snippet'"),
        {"id": snippet_id, "t": ctx["tenant_id"]},
    )
    existing = row.mappings().first()
    if not existing:
        raise HTTPException(404, "Not found")
    md = dict(existing["metadata"] or {})
    md["version"] = int(md.get("version", 1)) + 1
    md["topic_tags"] = req.topic_tags
    md["approved"] = False  # re-approval required
    await db.execute(
        text("UPDATE documents SET title = :ti, status = 'pending_approval' "
             "WHERE id = :id"),
        {"ti": req.title, "id": snippet_id},
    )
    # Re-embed the single chunk
    emb = _embedder.embed([req.body])[0]
    await db.execute(
        text("UPDATE chunks SET text = :t, metadata = CAST(:m AS jsonb), "
             "embedding = CAST(:e AS vector) WHERE document_id = :did"),
        {"t": req.body, "m": json.dumps(md),
         "e": _emb_to_vector(emb), "did": snippet_id},
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
        text("UPDATE documents SET status = 'archived' "
             "WHERE id = :id AND tenant_id = :t "
             "AND category = 'boilerplate_snippet'"),
        {"id": snippet_id, "t": ctx["tenant_id"]},
    )
    if (r.rowcount or 0) == 0:
        raise HTTPException(404, "Not found")
    await db.commit()
