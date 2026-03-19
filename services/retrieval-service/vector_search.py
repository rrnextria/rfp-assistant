from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from rbac_filter import UserContext, build_rbac_filter
except ImportError:
    from rbac_filter import UserContext, build_rbac_filter  # type: ignore[no-redef]


@dataclass
class RankedChunk:
    chunk_id: str
    doc_id: str
    text: str
    score: float
    metadata: dict
    embedding: list[float] | None = None


async def vector_search(
    db: AsyncSession,
    query_embedding: list[float],
    user_ctx: UserContext,
    extra_filters: dict | None = None,
    limit: int = 50,
) -> list[RankedChunk]:
    """
    Cosine distance search using pgvector.
    Returns chunks ordered by similarity (lower distance = higher relevance).
    """
    rbac_where = build_rbac_filter(user_ctx)

    # Format embedding for pgvector
    vec_str = f"[{','.join(str(v) for v in query_embedding)}]"

    where_clause = rbac_where

    sql = f"""
        SELECT
            id::text AS chunk_id,
            document_id::text AS doc_id,
            text,
            metadata,
            (embedding <=> '{vec_str}'::vector) AS score
        FROM chunks
        WHERE {where_clause}
        ORDER BY score ASC
        LIMIT {limit}
    """

    result = await db.execute(text(sql))
    rows = result.mappings().all()

    return [
        RankedChunk(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            text=row["text"],
            score=float(row["score"]),
            metadata=row["metadata"] if isinstance(row["metadata"], dict) else {},
        )
        for row in rows
    ]
