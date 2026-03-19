from __future__ import annotations

import sys
import pytest

sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/retrieval-service")


def make_chunk(cid, score=0.5):
    from vector_search import RankedChunk
    return RankedChunk(chunk_id=cid, doc_id="doc1", text="text", score=score, metadata={})


def test_rrf_deduplicates():
    from reranker import reciprocal_rank_fusion

    vec = [make_chunk("A", 0.1), make_chunk("B", 0.2)]
    kw = [make_chunk("B", 0.9), make_chunk("C", 0.5)]

    result = reciprocal_rank_fusion(vec, kw, k=60, top_n=5)
    ids = [r.chunk_id for r in result]
    assert len(ids) == len(set(ids)), "No duplicates"
    assert "B" in ids  # B appears in both → higher RRF score


def test_rrf_top_n():
    from reranker import reciprocal_rank_fusion

    vec = [make_chunk(str(i)) for i in range(20)]
    kw = [make_chunk(str(i + 5)) for i in range(20)]
    result = reciprocal_rank_fusion(vec, kw, k=60, top_n=12)
    assert len(result) <= 12


def test_rrf_score_adjustments():
    from reranker import reciprocal_rank_fusion

    vec = [make_chunk("A"), make_chunk("B")]
    kw = []
    # Boost chunk B
    result = reciprocal_rank_fusion(vec, kw, k=60, top_n=5, score_adjustments={"B": 10.0})
    ids = [r.chunk_id for r in result]
    assert ids[0] == "B", "Boosted chunk should rank first"
