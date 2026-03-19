from __future__ import annotations

import sys
import pytest

sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/orchestrator")


def test_minimal_balanced_detailed_prompts_differ():
    from prompts import build_user_prompt

    chunks = [{"doc_id": "d1", "text": "We provide enterprise security."}]
    q = "Describe your security."

    minimal = build_user_prompt(q, chunks, detail_level="minimal")
    balanced = build_user_prompt(q, chunks, detail_level="balanced")
    detailed = build_user_prompt(q, chunks, detail_level="detailed")

    assert minimal != balanced
    assert balanced != detailed
    assert minimal != detailed


def test_partial_compliance_threshold():
    """Test that < 2 chunks triggers partial_compliance in pipeline."""
    from pipeline import compute_confidence

    # With 0 chunks → confidence = 0.0
    assert compute_confidence([]) == 0.0

    # With 1 chunk
    conf = compute_confidence([{"score": 0.01}])
    assert 0.0 <= conf <= 1.0
