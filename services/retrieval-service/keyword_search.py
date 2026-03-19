from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from rbac_filter import UserContext, build_rbac_filter
    from vector_search import RankedChunk
except ImportError:
    from rbac_filter import UserContext, build_rbac_filter  # type: ignore[no-redef]
    from vector_search import RankedChunk  # type: ignore[no-redef]


async def keyword_search(
    db: AsyncSession,
    query: str,
    user_ctx: UserContext,
    limit: int = 50,
) -> list[RankedChunk]:
    """
    Full-text search using Postgres tsvector/tsquery.
    Uses ts_rank_cd scoring (cover density ranking).
    """
    rbac_where = build_rbac_filter(user_ctx)

    # Sanitize query for plainto_tsquery
    safe_query = query.replace("'", "''")

    sql = f"""
        SELECT
            c.id::text AS chunk_id,
            c.document_id::text AS doc_id,
            COALESCE(d.title, '') AS doc_title,
            c.text,
            c.metadata,
            ts_rank_cd(c.text_search, plainto_tsquery('english', '{safe_query}')) AS score
        FROM chunks c
        LEFT JOIN documents d ON d.id = c.document_id
        WHERE {rbac_where}
          AND c.text_search @@ plainto_tsquery('english', '{safe_query}')
        ORDER BY score DESC
        LIMIT {limit}
    """

    result = await db.execute(text(sql))
    rows = result.mappings().all()

    return [
        RankedChunk(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            doc_title=row["doc_title"] or "",
            text=row["text"],
            score=float(row["score"]),
            metadata=row["metadata"] if isinstance(row["metadata"], dict) else {},
        )
        for row in rows
    ]
