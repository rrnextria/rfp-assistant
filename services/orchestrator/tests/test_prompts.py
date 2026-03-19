from __future__ import annotations

import sys
import pytest

sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/orchestrator")


def test_system_prompt_not_empty():
    from prompts import build_system_prompt
    prompt = build_system_prompt()
    assert len(prompt) > 100
    assert "RFP" in prompt


def test_answer_mode_prompt():
    from prompts import build_user_prompt
    chunks = [{"doc_id": "d1", "text": "Company supports SSO via SAML 2.0."}]
    prompt = build_user_prompt("Does your product support SSO?", chunks, mode="answer")
    assert "SSO" in prompt
    assert "SAML" in prompt


def test_draft_mode_prompt_has_instruction():
    from prompts import build_user_prompt
    chunks = [{"doc_id": "d1", "text": "We offer 24/7 support."}]
    prompt = build_user_prompt("Describe your support model.", chunks, mode="draft")
    assert "Draft" in prompt or "draft" in prompt or "formal" in prompt.lower()


def test_review_mode_prompt_has_instruction():
    from prompts import build_user_prompt
    chunks = [{"doc_id": "d1", "text": "We offer SLA of 99.9%."}]
    prompt = build_user_prompt("What is your uptime guarantee?", chunks, mode="review")
    assert "Review" in prompt or "review" in prompt or "gap" in prompt.lower() or "risk" in prompt.lower()


def test_gap_mode_prompt_has_instruction():
    from prompts import build_user_prompt
    chunks = [{"doc_id": "d1", "text": "Some partial info."}]
    prompt = build_user_prompt("What certifications do you have?", chunks, mode="gap")
    assert "gap" in prompt.lower() or "missing" in prompt.lower()


def test_detail_level_minimal():
    from prompts import build_user_prompt
    chunks = [{"doc_id": "d1", "text": "We support ISO 27001."}]
    prompt = build_user_prompt("What certifications do you have?", chunks, detail_level="minimal")
    assert "concise" in prompt.lower() or "bullet" in prompt.lower() or "brief" in prompt.lower()


def test_detail_level_detailed():
    from prompts import build_user_prompt
    chunks = [{"doc_id": "d1", "text": "Full cert info."}]
    prompt = build_user_prompt("Describe your security posture.", chunks, detail_level="detailed")
    assert "comprehensive" in prompt.lower() or "narrative" in prompt.lower() or "detailed" in prompt.lower()
