from __future__ import annotations

try:
    from .vector_search import RankedChunk
except ImportError:
    from vector_search import RankedChunk  # type: ignore[no-redef]


def reciprocal_rank_fusion(
    vector_results: list[RankedChunk],
    keyword_results: list[RankedChunk],
    k: int = 60,
    top_n: int = 12,
    score_adjustments: dict[str, float] | None = None,
) -> list[RankedChunk]:
    """
    Combine vector and keyword results using Reciprocal Rank Fusion.

    RRF score = 1/(k + rank_v) + 1/(k + rank_k)

    Win/loss score adjustments are applied post-fusion:
    final_score = rrf_score * (1 + boost)
    """
    scores: dict[str, float] = {}
    chunk_data: dict[str, RankedChunk] = {}

    for rank, chunk in enumerate(vector_results, start=1):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
        chunk_data[chunk.chunk_id] = chunk

    for rank, chunk in enumerate(keyword_results, start=1):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
        if chunk.chunk_id not in chunk_data:
            chunk_data[chunk.chunk_id] = chunk

    # Apply win/loss score adjustments
    if score_adjustments:
        for chunk_id, boost in score_adjustments.items():
            if chunk_id in scores:
                scores[chunk_id] *= (1.0 + boost)

    # Sort by RRF score descending, take top_n
    sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)[:top_n]

    result = []
    for cid in sorted_ids:
        chunk = chunk_data[cid]
        result.append(RankedChunk(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            text=chunk.text,
            score=scores[cid],
            metadata=chunk.metadata,
        ))

    return result
