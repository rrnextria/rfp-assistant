from __future__ import annotations

try:
    from vector_search import RankedChunk
except ImportError:
    from vector_search import RankedChunk  # type: ignore[no-redef]


_DEFAULT_CATEGORY_BOOSTS: dict[str, float] = {
    "boilerplate_snippet": 0.15,
    "past_proposal_won":   0.10,
    "past_proposal_lost":  0.02,
    "contract":            0.05,
    "product_doc":         0.00,
    "general":             0.00,
}


def _category_boost_key(chunk: "RankedChunk") -> str:
    """For past_proposal chunks, split won/lost based on chunk.metadata.outcome."""
    if chunk.category == "past_proposal":
        outcome = (chunk.metadata or {}).get("outcome")
        if outcome == "won":
            return "past_proposal_won"
        if outcome == "lost":
            return "past_proposal_lost"
        return "general"
    return chunk.category


def apply_category_boost(rrf_score: float, chunk: "RankedChunk",
                          boosts: dict[str, float]) -> float:
    key = _category_boost_key(chunk)
    return rrf_score + boosts.get(key, 0.0)


def reciprocal_rank_fusion(
    vector_results: list[RankedChunk],
    keyword_results: list[RankedChunk],
    k: int = 60,
    top_n: int = 12,
    score_adjustments: dict[str, float] | None = None,
    category_boosts: dict[str, float] | None = None,
) -> list[RankedChunk]:
    """
    Combine vector and keyword results using Reciprocal Rank Fusion.

    RRF score = 1/(k + rank_v) + 1/(k + rank_k)
              + category_boost(chunk)
              * (1 + win/loss boost)
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

    # Category boosts: snippets, won past-proposals, contracts get a nudge
    boosts = category_boosts or _DEFAULT_CATEGORY_BOOSTS
    for chunk_id, chunk in chunk_data.items():
        scores[chunk_id] = apply_category_boost(scores[chunk_id], chunk, boosts)

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
            doc_title=chunk.doc_title,
            text=chunk.text,
            score=scores[cid],
            metadata=chunk.metadata,
        ))

    return result
