"""Tests for research.py — slugify, state management, ClaudeRunner, and ResearchLoop."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator_v3.approval import (
    ResearchResult,
    check_converged,
    parse_research_meta,
)
from orchestrator_v3.config import OrchestratorSettings
from orchestrator_v3.research import (
    ClaudeRunner,
    ResearchLoop,
    ResearchState,
    ResearchStateManager,
    _slugify,
)
from orchestrator_v3.research_prompts import ResearchPromptBuilder
from orchestrator_v3.reviewer import CodexReviewer


# ── TestSlugify ───────────────────────────────────────────────────────


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello_world"

    def test_stop_words_removed(self):
        result = _slugify("What are the tradeoffs between sync and async")
        assert "what" not in result
        assert "are" not in result
        assert "the" not in result
        assert "tradeoffs" in result

    def test_max_words(self):
        result = _slugify("one two three four five six seven", max_words=3)
        assert result.count("_") <= 2  # at most 3 words

    def test_empty(self):
        result = _slugify("")
        assert result == "research"

    def test_special_chars(self):
        result = _slugify("What's the best way? (really)")
        assert "'" not in result
        assert "(" not in result
        assert ")" not in result

    def test_length_cap(self):
        long_text = " ".join(f"word{i}" for i in range(20))
        result = _slugify(long_text, max_words=20)
        assert len(result) <= 60

    def test_all_stop_words(self):
        result = _slugify("is the a an")
        # Should fall back to using words without filtering
        assert len(result) > 0


# ── TestResearchState ─────────────────────────────────────────────────


class TestResearchState:
    def test_init(self, tmp_research_settings):
        research_dir = tmp_research_settings.research_dir / "test"
        research_dir.mkdir(parents=True)
        state_path = research_dir / "state.json"
        sm = ResearchStateManager(state_path=state_path)
        state = sm.init(slug="test", question="What is X?")
        assert state.slug == "test"
        assert state.question == "What is X?"
        assert state.status == "in_progress"
        assert state.current_phase == 1
        assert state.started_at

    def test_load_roundtrip(self, tmp_research_settings):
        research_dir = tmp_research_settings.research_dir / "test"
        research_dir.mkdir(parents=True)
        state_path = research_dir / "state.json"
        sm = ResearchStateManager(state_path=state_path)
        sm.init(slug="test", question="What is X?", max_rounds=5)
        loaded = sm.load()
        assert loaded.slug == "test"
        assert loaded.max_rounds == 5

    def test_update(self, tmp_research_settings):
        research_dir = tmp_research_settings.research_dir / "test"
        research_dir.mkdir(parents=True)
        state_path = research_dir / "state.json"
        sm = ResearchStateManager(state_path=state_path)
        sm.init(slug="test", question="What is X?")
        updated = sm.update(intent="DEBUGGING", current_phase=2)
        assert updated.intent == "DEBUGGING"
        assert updated.current_phase == 2

    def test_unknown_field_rejected(self, tmp_research_settings):
        research_dir = tmp_research_settings.research_dir / "test"
        research_dir.mkdir(parents=True)
        state_path = research_dir / "state.json"
        sm = ResearchStateManager(state_path=state_path)
        sm.init(slug="test", question="What is X?")
        with pytest.raises(ValueError, match="Unknown research state fields"):
            sm.update(nonexistent_field="bad")

    def test_backup_creation(self, tmp_research_settings):
        research_dir = tmp_research_settings.research_dir / "test"
        research_dir.mkdir(parents=True)
        state_path = research_dir / "state.json"
        sm = ResearchStateManager(state_path=state_path)
        sm.init(slug="test", question="What is X?")
        # First save creates the file, second creates .bak
        sm.update(intent="CLEAN_QUESTION")
        assert Path(str(state_path) + ".bak").exists()

    def test_record_event(self, tmp_research_settings):
        research_dir = tmp_research_settings.research_dir / "test"
        research_dir.mkdir(parents=True)
        state_path = research_dir / "state.json"
        sm = ResearchStateManager(state_path=state_path)
        sm.init(slug="test", question="What is X?")
        sm.record_event(
            phase=1, model="opus", action="initial_analysis",
            artifact="opus_initial.md",
        )
        state = sm.load()
        assert len(state.history) == 1
        assert state.history[0]["phase"] == 1
        assert state.history[0]["model"] == "opus"


# ── TestParseResearchMeta ─────────────────────────────────────────────


class TestParseResearchMeta:
    def test_valid_converged(self, tmp_path):
        p = tmp_path / "converged.md"
        p.write_text(
            "<!-- RESEARCH_META\n"
            "AGREEMENT: 9\n"
            "OPEN_ISSUES: 0\n"
            "DELTA: Minor wording only\n"
            "-->\n\n"
            "# Analysis\n"
        )
        result = parse_research_meta(p)
        assert result is not None
        assert result.agreement == 9
        assert result.open_issues == 0
        assert result.delta == "Minor wording only"

    def test_valid_not_converged(self, tmp_path):
        p = tmp_path / "not_converged.md"
        p.write_text(
            "<!-- RESEARCH_META\n"
            "AGREEMENT: 5\n"
            "OPEN_ISSUES: 3\n"
            "DELTA: Still disagreeing on caching\n"
            "-->\n"
        )
        result = parse_research_meta(p)
        assert result is not None
        assert result.agreement == 5
        assert result.open_issues == 3

    def test_missing_block(self, tmp_path):
        p = tmp_path / "no_meta.md"
        p.write_text("# Just some markdown\nNo meta block here.\n")
        result = parse_research_meta(p)
        assert result is None

    def test_malformed_non_numeric(self, tmp_path):
        p = tmp_path / "malformed.md"
        p.write_text(
            "<!-- RESEARCH_META\n"
            "AGREEMENT: high\n"
            "OPEN_ISSUES: 0\n"
            "-->\n"
        )
        result = parse_research_meta(p)
        assert result is None

    def test_missing_required_key(self, tmp_path):
        p = tmp_path / "missing.md"
        p.write_text(
            "<!-- RESEARCH_META\n"
            "AGREEMENT: 8\n"
            "-->\n"
        )
        result = parse_research_meta(p)
        assert result is None

    def test_file_not_found(self, tmp_path):
        p = tmp_path / "nonexistent.md"
        result = parse_research_meta(p)
        assert result is None


# ── TestCheckConverged ────────────────────────────────────────────────


class TestCheckConverged:
    def test_threshold_met(self, tmp_path):
        p = tmp_path / "conv.md"
        p.write_text(
            "<!-- RESEARCH_META\n"
            "AGREEMENT: 8\n"
            "OPEN_ISSUES: 0\n"
            "DELTA: Fully aligned\n"
            "-->\n"
        )
        assert check_converged(p) is True

    def test_high_agreement(self, tmp_path):
        p = tmp_path / "conv.md"
        p.write_text(
            "<!-- RESEARCH_META\n"
            "AGREEMENT: 10\n"
            "OPEN_ISSUES: 0\n"
            "DELTA: Perfect alignment\n"
            "-->\n"
        )
        assert check_converged(p) is True

    def test_low_agreement(self, tmp_path):
        p = tmp_path / "conv.md"
        p.write_text(
            "<!-- RESEARCH_META\n"
            "AGREEMENT: 7\n"
            "OPEN_ISSUES: 0\n"
            "DELTA: Almost there\n"
            "-->\n"
        )
        assert check_converged(p) is False

    def test_open_issues_blocks(self, tmp_path):
        p = tmp_path / "conv.md"
        p.write_text(
            "<!-- RESEARCH_META\n"
            "AGREEMENT: 9\n"
            "OPEN_ISSUES: 1\n"
            "DELTA: One issue remaining\n"
            "-->\n"
        )
        assert check_converged(p) is False

    def test_missing_file(self, tmp_path):
        p = tmp_path / "nonexistent.md"
        assert check_converged(p) is False


# ── TestClaudeRunner ──────────────────────────────────────────────────


class TestClaudeRunner:
    def test_success(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        # Mock subprocess.Popen
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout.read1 = MagicMock(
            side_effect=[b"Hello from Claude", b""]
        )
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock()

        with patch("orchestrator_v3.research.subprocess.Popen", return_value=mock_proc):
            result = runner.run("test prompt", output_file, log_file)

        assert result is True
        assert output_file.exists()
        assert output_file.read_text() == "Hello from Claude"

    def test_binary_not_found(self, tmp_path):
        runner = ClaudeRunner()
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        with patch(
            "orchestrator_v3.research.subprocess.Popen",
            side_effect=FileNotFoundError("claude not found"),
        ):
            result = runner.run("test", output_file, log_file)

        assert result is False

    def test_nonzero_exit(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout.read1 = MagicMock(side_effect=[b"error", b""])
        mock_proc.returncode = 1
        mock_proc.wait = MagicMock()

        with patch("orchestrator_v3.research.subprocess.Popen", return_value=mock_proc):
            result = runner.run("test", output_file, log_file)

        assert result is False


# ── Mock Runners ──────────────────────────────────────────────────────


class MockClaudeRunner:
    """Test double that writes predetermined content to output files."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, Path]] = []
        self.timeout: int = 1800
        self.proc: None = None

    def run(self, prompt: str, output_file: Path, log_file: Path) -> bool:
        self.calls.append((prompt, output_file))
        output_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Find response by matching output file name
        content = self.responses.get(output_file.name, "Mock response")
        output_file.write_text(content)
        log_file.write_text(f"[MockClaude] Wrote {output_file.name}")
        return True


class MockCodexRunner:
    """Test double for CodexReviewer that writes predetermined content."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, Path]] = []
        self.timeout: int = 600
        self.proc: None = None

    def run_review(self, prompt: str, review_file: Path, log_file: Path) -> bool:
        self.calls.append((prompt, review_file))
        review_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        content = self.responses.get(review_file.name, "Mock Codex response")
        review_file.write_text(content)
        # _run_codex() reads from log_file and strips the Codex banner,
        # so the log must contain the response wrapped in the Codex format.
        log_file.write_text(f"codex\n{content}")
        return True


# ── TestResearchLoopIntegration ───────────────────────────────────────

_CONVERGED_META = """\
<!-- RESEARCH_META
AGREEMENT: 9
OPEN_ISSUES: 0
DELTA: Fully aligned
-->

# Converged Analysis
Both models agree.
"""

_NOT_CONVERGED_META = """\
<!-- RESEARCH_META
AGREEMENT: 5
OPEN_ISSUES: 2
DELTA: Still divergent
-->

# Divergent Analysis
Models disagree on key points.
"""


class TestResearchLoopIntegration:
    def _make_loop(self, tmp_research_settings, claude_responses, codex_responses):
        slug = "test_research"
        research_dir = tmp_research_settings.research_dir / slug
        research_dir.mkdir(parents=True)
        state_path = research_dir / "state.json"

        sm = ResearchStateManager(state_path=state_path)
        sm.init(slug=slug, question="Test question?", max_rounds=10)

        pb = ResearchPromptBuilder(question="Test question?", intent="", slug=slug)
        claude = MockClaudeRunner(responses=claude_responses)
        codex = MockCodexRunner(responses=codex_responses)
        display = MagicMock()

        loop = ResearchLoop(
            state_manager=sm,
            prompt_builder=pb,
            claude_runner=claude,
            codex_runner=codex,
            display=display,
            settings=tmp_research_settings,
            slug=slug,
        )
        return loop, sm, claude, codex

    def test_full_loop_converges_round_1(self, tmp_research_settings):
        claude_responses = {
            "intent_classification.md": "CLEAN_QUESTION",
            "opus_initial.md": "Opus initial analysis",
            "opus_cross_review.md": "Opus cross-review",
            "opus_convergence_r1.md": _CONVERGED_META,
            "synthesis.md": "# Synthesis\nFinal answer.",
        }
        codex_responses = {
            "codex_initial.md": "Codex initial analysis",
            "codex_cross_review.md": "Codex cross-review",
            "codex_convergence_r1.md": _CONVERGED_META,
        }

        loop, sm, claude, codex = self._make_loop(
            tmp_research_settings, claude_responses, codex_responses,
        )
        result = loop.run(max_rounds=5)

        assert result == 0
        state = sm.load()
        assert state.status == "complete"
        assert state.current_phase == 4
        assert state.opus_agreement == 9
        assert state.codex_agreement == 9
        assert state.open_issues == 0

        # Verify artifacts were created
        research_dir = tmp_research_settings.research_dir / "test_research"
        assert (research_dir / "opus_initial.md").exists()
        assert (research_dir / "codex_initial.md").exists()
        assert (research_dir / "synthesis.md").exists()

    def test_max_rounds_reached(self, tmp_research_settings):
        claude_responses = {
            "intent_classification.md": "INVESTIGATION",
            "opus_initial.md": "Opus initial",
            "opus_cross_review.md": "Opus cross-review",
            "opus_convergence_r1.md": _NOT_CONVERGED_META,
            "opus_convergence_r2.md": _NOT_CONVERGED_META,
            "synthesis.md": "# Synthesis\nBest effort.",
        }
        codex_responses = {
            "codex_initial.md": "Codex initial",
            "codex_cross_review.md": "Codex cross-review",
            "codex_convergence_r1.md": _NOT_CONVERGED_META,
            "codex_convergence_r2.md": _NOT_CONVERGED_META,
        }

        loop, sm, _, _ = self._make_loop(
            tmp_research_settings, claude_responses, codex_responses,
        )
        result = loop.run(max_rounds=2)

        assert result == 0
        state = sm.load()
        assert state.status == "complete"  # Still completes with synthesis
        assert state.convergence_round == 2

    def test_phase1_failure_aborts(self, tmp_research_settings):
        """If Opus fails in Phase 1, the loop returns error."""
        slug = "test_fail"
        research_dir = tmp_research_settings.research_dir / slug
        research_dir.mkdir(parents=True)
        state_path = research_dir / "state.json"

        sm = ResearchStateManager(state_path=state_path)
        sm.init(slug=slug, question="Fail test?", max_rounds=5)

        pb = ResearchPromptBuilder(question="Fail test?", intent="", slug=slug)

        # Claude succeeds on intent classification but fails on initial analysis
        claude = MockClaudeRunner(
            responses={"intent_classification.md": "CLEAN_QUESTION"},
        )
        # Override run to fail on opus_initial.md
        original_run = claude.run

        def failing_run(prompt, output_file, log_file):
            if output_file.name == "opus_initial.md":
                return False
            return original_run(prompt, output_file, log_file)

        claude.run = failing_run

        codex = MockCodexRunner()
        display = MagicMock()

        loop = ResearchLoop(
            state_manager=sm, prompt_builder=pb, claude_runner=claude,
            codex_runner=codex, display=display, settings=tmp_research_settings,
            slug=slug,
        )
        result = loop.run(max_rounds=3)

        assert result == 1
        state = sm.load()
        assert state.status == "error"

    def test_intent_classification_fallback(self, tmp_research_settings):
        """If intent classification returns garbage, falls back to CLEAN_QUESTION."""
        claude_responses = {
            "intent_classification.md": "I don't understand the question",
            "opus_initial.md": "Opus analysis",
            "opus_cross_review.md": "Opus review",
            "opus_convergence_r1.md": _CONVERGED_META,
            "synthesis.md": "# Synthesis",
        }
        codex_responses = {
            "codex_initial.md": "Codex analysis",
            "codex_cross_review.md": "Codex review",
            "codex_convergence_r1.md": _CONVERGED_META,
        }

        loop, sm, _, _ = self._make_loop(
            tmp_research_settings, claude_responses, codex_responses,
        )
        result = loop.run(max_rounds=3)

        assert result == 0
        state = sm.load()
        assert state.intent == "CLEAN_QUESTION"
