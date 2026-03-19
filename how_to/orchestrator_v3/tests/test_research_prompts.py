"""Tests for research_prompts.py — prompt template verification."""

from __future__ import annotations

import pytest

from orchestrator_v3.research_prompts import INTENT_TYPES, ResearchPromptBuilder


class TestIntentClassificationPrompt:
    def test_contains_all_intent_types(self):
        prompt = ResearchPromptBuilder.build_intent_classification_prompt(
            "What is async IO?"
        )
        for intent in INTENT_TYPES:
            assert intent in prompt

    def test_contains_question(self):
        q = "How does garbage collection work in Python?"
        prompt = ResearchPromptBuilder.build_intent_classification_prompt(q)
        assert q in prompt


class TestInitialAnalysisPrompt:
    def test_contains_model_name(self):
        pb = ResearchPromptBuilder("Test Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_initial_analysis_prompt("Opus (Claude)")
        assert "Opus (Claude)" in prompt

    def test_contains_question(self):
        q = "What are sync vs async tradeoffs?"
        pb = ResearchPromptBuilder(q, "CLEAN_QUESTION", "test")
        prompt = pb.build_initial_analysis_prompt("Opus")
        assert q in prompt

    def test_contains_intent(self):
        pb = ResearchPromptBuilder("Q?", "DEBUGGING", "test")
        prompt = pb.build_initial_analysis_prompt("Opus")
        assert "DEBUGGING" in prompt
        assert "root causes" in prompt

    def test_seed_response_included(self):
        pb = ResearchPromptBuilder("Q?", "SEED_RESPONSE", "test")
        prompt = pb.build_initial_analysis_prompt(
            "Opus", seed_response="My initial answer is X."
        )
        assert "My initial answer is X." in prompt

    def test_context_files_included(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_initial_analysis_prompt(
            "Opus", context_files=["src/main.py", "tests/test_main.py"]
        )
        assert "src/main.py" in prompt
        assert "tests/test_main.py" in prompt

    def test_all_intent_types_produce_prompt(self):
        for intent in INTENT_TYPES:
            pb = ResearchPromptBuilder("Q?", intent, "test")
            prompt = pb.build_initial_analysis_prompt("Opus")
            assert len(prompt) > 100


class TestCrossReviewPrompt:
    def test_contains_both_positions(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_cross_review_prompt(
            "Opus", "My analysis is A.", "Their analysis is B.", "Codex"
        )
        assert "My analysis is A." in prompt
        assert "Their analysis is B." in prompt

    def test_contains_model_names(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_cross_review_prompt(
            "Opus", "A", "B", "Codex"
        )
        assert "Opus" in prompt
        assert "Codex" in prompt

    def test_contains_question(self):
        q = "Complex question here?"
        pb = ResearchPromptBuilder(q, "CLEAN_QUESTION", "test")
        prompt = pb.build_cross_review_prompt("Opus", "A", "B", "Codex")
        assert q in prompt


class TestConvergencePrompt:
    def test_contains_research_meta_instructions(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_convergence_prompt(
            "Opus", "My latest", "Their latest", "Codex", 1
        )
        assert "RESEARCH_META" in prompt
        assert "AGREEMENT" in prompt
        assert "OPEN_ISSUES" in prompt

    def test_contains_round_num(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_convergence_prompt(
            "Opus", "A", "B", "Codex", 3
        )
        assert "round 3" in prompt or "Round 3" in prompt

    def test_contains_both_positions(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_convergence_prompt(
            "Opus", "Position A", "Position B", "Codex", 1
        )
        assert "Position A" in prompt
        assert "Position B" in prompt


class TestSynthesisPrompt:
    def test_contains_both_finals(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_synthesis_prompt(
            "Opus final position", "Codex final position", []
        )
        assert "Opus final position" in prompt
        assert "Codex final position" in prompt

    def test_contains_question(self):
        q = "What is the meaning?"
        pb = ResearchPromptBuilder(q, "CLEAN_QUESTION", "test")
        prompt = pb.build_synthesis_prompt("A", "B", [])
        assert q in prompt

    def test_convergence_history_included(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        history = [
            {"model": "opus", "round": 1, "agreement": 6, "open_issues": 2, "delta": "Narrowed gap"},
            {"model": "codex", "round": 1, "agreement": 7, "open_issues": 1, "delta": "Closer"},
        ]
        prompt = pb.build_synthesis_prompt("A", "B", history)
        assert "Narrowed gap" in prompt
        assert "Closer" in prompt
        assert "Round 1" in prompt

    def test_empty_history(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_synthesis_prompt("A", "B", [])
        assert "No convergence rounds recorded" in prompt

    def test_required_sections(self):
        pb = ResearchPromptBuilder("Q?", "CLEAN_QUESTION", "test")
        prompt = pb.build_synthesis_prompt("A", "B", [])
        assert "### Agreement" in prompt
        assert "### Disagreement" in prompt
        assert "### Synthesis" in prompt
        assert "### Recommendations" in prompt
