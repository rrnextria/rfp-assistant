from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from common.embedder import SentenceTransformerEmbedder
from keyword_search import keyword_search
from rbac_filter import UserContext
from reranker import reciprocal_rank_fusion
from vector_search import RankedChunk, vector_search

_embedder = SentenceTransformerEmbedder()


async def retrieve(
    db: AsyncSession,
    query: str,
    user_ctx: UserContext,
    filters: dict | None = None,
    top_n: int = 12,
    score_adjustments: dict[str, float] | None = None,
) -> list[RankedChunk]:
    """
    Full retrieval pipeline:
    1. Embed query
    2. Run vector search + keyword search in parallel
    3. Apply Reciprocal Rank Fusion
    4. Return top_n chunks
    """
    # Embed query
    query_embedding = _embedder.embed([query])[0]

    # Run searches in parallel
    vec_results, kw_results = await asyncio.gather(
        vector_search(db, query_embedding, user_ctx, filters, limit=50),
        keyword_search(db, query, user_ctx, limit=50),
    )

    # Fuse and re-rank
    return reciprocal_rank_fusion(
        vec_results,
        kw_results,
        k=60,
        top_n=top_n,
        score_adjustments=score_adjustments,
    )
