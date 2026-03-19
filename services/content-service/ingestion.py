from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.embedder import SentenceTransformerEmbedder
from common.logging import get_logger
from chunker import chunk_sections
from parser import parse_pdf, parse_docx
from schemas import DocumentMetadata

logger = get_logger("content-service.ingestion")
_embedder = SentenceTransformerEmbedder()


async def ingest_document(
    db: AsyncSession,
    document_id: str,
    file_bytes: bytes,
    filename: str,
    metadata: DocumentMetadata,
) -> None:
    """Parse → chunk → embed → store chunks. Updates document status."""
    await db.execute(
        text("UPDATE documents SET status = 'processing' WHERE id = :id"),
        {"id": document_id},
    )
    await db.commit()

    try:
        # Parse
        if filename.lower().endswith(".pdf"):
            sections = parse_pdf(file_bytes)
        else:
            sections = parse_docx(file_bytes)

        # Chunk
        chunks = chunk_sections(sections)

        if not chunks:
            logger.warning(f"No chunks produced for document {document_id}")
            await db.execute(
                text("UPDATE documents SET status = 'ready' WHERE id = :id"),
                {"id": document_id},
            )
            await db.commit()
            return

        # Embed
        texts = [c.text for c in chunks]
        embeddings = _embedder.embed(texts)

        # Bulk insert
        meta_base = {
            "product": metadata.product,
            "region": metadata.region,
            "industry": metadata.industry,
            "allowed_teams": metadata.allowed_teams,
            "allowed_roles": metadata.allowed_roles,
            "approved": False,
        }

        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = str(uuid.uuid4())
            meta = {**meta_base, "heading": chunk.heading}
            # Insert chunk with embedding
            await db.execute(
                text(
                    "INSERT INTO chunks (id, document_id, text, metadata, embedding) "
                    "VALUES (:id, :doc_id, :text, :meta::jsonb, :emb::vector)"
                ),
                {
                    "id": chunk_id,
                    "doc_id": document_id,
                    "text": chunk.text,
                    "meta": json.dumps(meta),
                    "emb": f"[{','.join(str(v) for v in embedding)}]",
                },
            )

        await db.execute(
            text("UPDATE documents SET status = 'ready' WHERE id = :id"),
            {"id": document_id},
        )
        await db.commit()
        logger.info(f"Ingested {len(chunks)} chunks for document {document_id}")

    except Exception as exc:
        logger.error(f"Ingestion failed for {document_id}: {exc}")
        await db.execute(
            text("UPDATE documents SET status = 'error' WHERE id = :id"),
            {"id": document_id},
        )
        await db.commit()
        raise
