from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db, get_engine
from common.logging import get_logger
from agents import QuestionnaireExtractionAgent, RequirementExtractionAgent
from ingestion import ingest_document
from parser import parse_docx, parse_pdf
from schemas import DocumentMetadata

logger = get_logger("content-service")
req_agent = RequirementExtractionAgent()
q_agent = QuestionnaireExtractionAgent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting content-service")
    get_engine()
    yield
    await get_engine().dispose()


app = FastAPI(title="content-service", lifespan=lifespan)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "content-service"}


@app.get("/documents")
async def list_documents(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """List all documents with status."""
    rows = await db.execute(
        text(
            "SELECT id, title, status, created_by, created_at "
            "FROM documents ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        ),
        {"limit": limit, "offset": offset},
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "status": r["status"],
            "created_by": str(r["created_by"]) if r["created_by"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows.mappings().all()
    ]


@app.post("/documents", status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF/DOCX document for ingestion. Requires content_admin role."""
    # Parse metadata
    try:
        meta_dict = json.loads(metadata)
        doc_metadata = DocumentMetadata(**meta_dict)
    except Exception as e:
        raise HTTPException(400, f"Invalid metadata: {e}")

    # Validate file type
    if not file.filename or not file.filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(400, "Only PDF and DOCX files are supported")

    # Read file
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 50MB)")

    # Create document record
    document_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO documents (id, title, status) VALUES (:id, :title, 'pending')"
        ),
        {"id": document_id, "title": file.filename},
    )
    await db.commit()

    # Trigger ingestion in background
    background_tasks.add_task(
        ingest_document,
        db,
        document_id,
        file_bytes,
        file.filename,
        doc_metadata,
    )

    return {"document_id": document_id}


@app.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and all its chunks."""
    row = await db.execute(
        text("SELECT id FROM documents WHERE id = :id"), {"id": document_id}
    )
    if not row.first():
        raise HTTPException(404, "Document not found")
    await db.execute(text("DELETE FROM chunks WHERE document_id = :id"), {"id": document_id})
    await db.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})
    await db.commit()


@app.patch("/documents/{document_id}/approve")
async def approve_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Approve a document — sets status=approved and marks all chunks as approved."""
    # Verify document exists
    row = await db.execute(
        text("SELECT id FROM documents WHERE id = :id"), {"id": document_id}
    )
    if not row.first():
        raise HTTPException(404, "Document not found")

    await db.execute(
        text("UPDATE documents SET status = 'approved' WHERE id = :id"),
        {"id": document_id},
    )
    await db.execute(
        text(
            "UPDATE chunks SET metadata = metadata || jsonb_build_object('approved', true) "
            "WHERE document_id = :doc_id"
        ),
        {"doc_id": document_id},
    )
    await db.commit()
    return {"status": "approved", "document_id": document_id}


@app.post("/rfps/{rfp_id}/ingest", status_code=202)
async def ingest_rfp(
    rfp_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Ingest an RFP document: extract raw text, requirements, and questionnaire items."""
    # Verify RFP exists
    row = await db.execute(text("SELECT id FROM rfps WHERE id = :id"), {"id": rfp_id})
    if not row.first():
        raise HTTPException(404, "RFP not found")

    file_bytes = await file.read()

    async def _do_ingest():
        # Parse document
        if file.filename and file.filename.lower().endswith(".pdf"):
            sections = parse_pdf(file_bytes)
        else:
            sections = parse_docx(file_bytes)

        raw_text = "\n\n".join(s.text for s in sections if s.text)

        # Store raw text on rfp
        await db.execute(
            text("UPDATE rfps SET raw_text = :raw WHERE id = :id"),
            {"raw": raw_text, "id": rfp_id},
        )
        await db.commit()

        # Extract requirements and questionnaire items
        await req_agent.extract_and_store(db, rfp_id, raw_text)
        await q_agent.extract_and_store(db, rfp_id, raw_text)

    background_tasks.add_task(_do_ingest)
    return {"status": "processing", "rfp_id": rfp_id}
