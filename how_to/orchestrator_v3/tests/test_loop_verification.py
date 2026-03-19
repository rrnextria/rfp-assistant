"""Integration tests for plan verification gates in the orchestrator loop.

Tests cover all gate matrix rows from Phase 3 (loop integration):
- Phase-stage round: check_cross_file=False
- Master-stage round: check_cross_file=True
- Simple-plan round: check_cross_file=False
- plan --init (complex): check_cross_file=True at CLI entry
- code --init: check_cross_file=True at CLI entry
- code --resume: check_cross_file=True at CLI entry
- code-mode loop does NOT call _run_plan_verification
- --skip-preflight bypasses verification
- Warnings log but do not block
- Verification failure produces actionable output (line numbers, suggestions)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator_v3.artifacts import ArtifactResolver
from orchestrator_v3.config import Mode, OrchestratorSettings, PlanType, Status
from orchestrator_v3.loop import OrchestratorLoop, ReviewOutcome
from orchestrator_v3.plan_tool import PlanVerificationIssue, PlanVerificationResult
from orchestrator_v3.prompts import PromptBuilder
from orchestrator_v3.reviewer import MockReviewer
from orchestrator_v3.state import StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

APPROVED_ORCH_META = """\
<!-- ORCH_META
VERDICT: APPROVED
BLOCKER: 0
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 5
-->

# Review
All good.
"""

FIXES_REQUIRED_ORCH_META = """\
<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 1
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 3
-->

# Review
B1: Something is wrong.
"""


class StubDisplay:
    """Minimal display stub that records calls."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def stub(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return stub


def _make_passing_result() -> PlanVerificationResult:
    """Return a PlanVerificationResult with no issues (passing)."""
    return PlanVerificationResult(
        passed=True, issues=[], summary="PASSED (0 errors, 0 warnings)"
    )


def _make_warning_result() -> PlanVerificationResult:
    """Return a PlanVerificationResult with warnings but no errors."""
    return PlanVerificationResult(
        passed=True,
        issues=[
            PlanVerificationIssue(
                severity="warning",
                message="Section 'Risks & Mitigations' not found",
                line_number=None,
                suggestion="Add a ## Risks & Mitigations section",
            ),
        ],
        summary="PASSED (0 errors, 1 warning)",
    )


def _make_failing_result() -> PlanVerificationResult:
    """Return a PlanVerificationResult with errors (failing)."""
    return PlanVerificationResult(
        passed=False,
        issues=[
            PlanVerificationIssue(
                severity="error",
                message="Task heading malformed: '### [] 1 Task' missing space in checkbox",
                line_number=42,
                suggestion="Use '### [ ] 1 Task' with a space inside brackets",
            ),
            PlanVerificationIssue(
                severity="warning",
                message="Section 'Risks & Mitigations' not found",
                line_number=None,
                suggestion="Add a ## Risks & Mitigations section",
            ),
        ],
        summary="1 error, 1 warning",
    )


def _make_plan_loop(
    tmp_settings: OrchestratorSettings,
    plan_type: PlanType = PlanType.SIMPLE,
    stage_files: list[str] | None = None,
    current_stage: int = 0,
    total_stages: int = 1,
    skip_preflight: bool = False,
    mock_dir: Path | None = None,
    plan_file: str = "plan.md",
) -> tuple[OrchestratorLoop, StateManager, StubDisplay]:
    """Helper to create a plan-mode OrchestratorLoop with standard dependencies."""
    sm = StateManager(
        state_path=tmp_settings.reviews_dir / "test_orchestrator_state.json",
        settings=tmp_settings,
    )
    sm.init(
        plan_slug="test_slug",
        mode=Mode.PLAN,
        plan_file=plan_file,
        plan_type=plan_type,
        total_stages=total_stages,
        stage_files=stage_files or [plan_file],
        current_stage=current_stage,
    )
    resolver = ArtifactResolver(
        slug="test_slug", mode=Mode.PLAN, phase=0, task=1,
        settings=tmp_settings,
    )
    pb = PromptBuilder(
        artifact_resolver=resolver, mode=Mode.PLAN, slug="test_slug",
    )
    if mock_dir is None:
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
    reviewer = MockReviewer(mock_dir=mock_dir)
    disp = StubDisplay()
    loop = OrchestratorLoop(
        state_manager=sm,
        artifact_resolver=resolver,
        prompt_builder=pb,
        reviewer=reviewer,
        display=disp,
        settings=tmp_settings,
        skip_preflight=skip_preflight,
    )
    return loop, sm, disp


def _make_code_loop(
    tmp_settings: OrchestratorSettings,
    skip_preflight: bool = True,
    mock_dir: Path | None = None,
) -> tuple[OrchestratorLoop, StateManager, StubDisplay]:
    """Helper to create a code-mode OrchestratorLoop."""
    sm = StateManager(
        state_path=tmp_settings.reviews_dir / "test_code_state.json",
        settings=tmp_settings,
    )
    sm.init(
        plan_slug="test_slug",
        mode=Mode.CODE,
        plan_file="plan.md",
        plan_type=PlanType.SIMPLE,
    )
    resolver = ArtifactResolver(
        slug="test_slug", mode=Mode.CODE, phase=0, task=1,
        settings=tmp_settings,
    )
    pb = PromptBuilder(
        artifact_resolver=resolver, mode=Mode.CODE, slug="test_slug",
    )
    if mock_dir is None:
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
    reviewer = MockReviewer(mock_dir=mock_dir)
    disp = StubDisplay()
    loop = OrchestratorLoop(
        state_manager=sm,
        artifact_resolver=resolver,
        prompt_builder=pb,
        reviewer=reviewer,
        display=disp,
        settings=tmp_settings,
        skip_preflight=skip_preflight,
    )
    return loop, sm, disp


# ---------------------------------------------------------------------------
# Test 7.1: Well-formed plan passes verification gate
# ---------------------------------------------------------------------------


class TestWellFormedPlanPasses:
    """Well-formed plan passes verification and proceeds to reviewer."""

    @patch("orchestrator_v3.loop.verify_plan_syntax")
    def test_wellformed_plan_passes_verification(self, mock_verify, tmp_settings):
        """A passing verification result allows the round to proceed to reviewer."""
        mock_verify.return_value = _make_passing_result()
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        loop, sm, disp = _make_plan_loop(tmp_settings, mock_dir=mock_dir)
        outcome = loop.run_review_round(1)

        # Should NOT be PREFLIGHT_FAILED — verification passed
        assert outcome != ReviewOutcome.PREFLIGHT_FAILED
        # verify_plan_syntax was called
        mock_verify.assert_called_once()


# ---------------------------------------------------------------------------
# Test 7.2: Malformed plan fails verification, blocks reviewer
# ---------------------------------------------------------------------------


class TestMalformedPlanBlocksReviewer:
    """Malformed plan fails verification and blocks reviewer invocation."""

    @patch("orchestrator_v3.loop.verify_plan_syntax")
    def test_malformed_plan_blocks_reviewer(self, mock_verify, tmp_settings):
        """Verification failure returns PREFLIGHT_FAILED and reviewer never runs."""
        mock_verify.return_value = _make_failing_result()
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
        # Even if mock reviewer has a file, it should never be reached
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        loop, sm, disp = _make_plan_loop(tmp_settings, mock_dir=mock_dir)
        outcome = loop.run_review_round(1)

        assert outcome == ReviewOutcome.PREFLIGHT_FAILED
        # State should be NEEDS_RESPONSE
        state = sm.load()
        assert state.status == Status.NEEDS_RESPONSE.value
        # print_verification_failure was called
        verification_calls = [
            c for c in disp.calls if c[0] == "print_verification_failure"
        ]
        assert len(verification_calls) == 1


# ---------------------------------------------------------------------------
# Test 7.3: --skip-preflight bypasses verification
# ---------------------------------------------------------------------------


class TestSkipPreflightBypassesVerification:
    """--skip-preflight bypasses both preflight and verification."""

    @patch("orchestrator_v3.loop.verify_plan_syntax")
    def test_skip_preflight_bypasses_verification(self, mock_verify, tmp_settings):
        """With skip_preflight=True, verify_plan_syntax is never called."""
        mock_verify.return_value = _make_failing_result()
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        loop, sm, disp = _make_plan_loop(
            tmp_settings, skip_preflight=True, mock_dir=mock_dir
        )
        outcome = loop.run_review_round(1)

        # Should NOT fail — skip_preflight bypasses verification
        assert outcome != ReviewOutcome.PREFLIGHT_FAILED
        # verify_plan_syntax should NOT have been called
        mock_verify.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7.4: Phase-stage round uses check_cross_file=False
# ---------------------------------------------------------------------------


class TestPhaseStageUsesNoCrossFile:
    """Phase-stage round calls verify_plan_syntax with check_cross_file=False."""

    @patch("orchestrator_v3.loop.verify_plan_syntax")
    def test_phase_stage_check_cross_file_false(self, mock_verify, tmp_settings):
        mock_verify.return_value = _make_passing_result()
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        phase_file = str(tmp_settings.active_plans_dir / "phase_0.md")
        master_file = str(tmp_settings.active_plans_dir / "master.md")
        # Write the files so they exist
        Path(phase_file).write_text("# Phase 0\n")
        Path(master_file).write_text("# Master\n")

        loop, sm, disp = _make_plan_loop(
            tmp_settings,
            plan_type=PlanType.COMPLEX,
            stage_files=[phase_file, master_file],
            current_stage=0,  # phase stage (not last)
            total_stages=2,
            mock_dir=mock_dir,
        )
        loop.run_review_round(1)

        mock_verify.assert_called_once()
        call_kwargs = mock_verify.call_args
        assert call_kwargs.kwargs.get("check_cross_file") is False
        # Target should be the phase file
        assert str(call_kwargs.args[0]) == phase_file


# ---------------------------------------------------------------------------
# Test 7.5: Master-stage round uses check_cross_file=True
# ---------------------------------------------------------------------------


class TestMasterStageUsesCrossFile:
    """Master-stage round calls verify_plan_syntax with check_cross_file=True."""

    @patch("orchestrator_v3.loop.verify_plan_syntax")
    def test_master_stage_check_cross_file_true(self, mock_verify, tmp_settings):
        mock_verify.return_value = _make_passing_result()
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        phase_file = str(tmp_settings.active_plans_dir / "phase_0.md")
        master_file = str(tmp_settings.active_plans_dir / "master.md")
        Path(phase_file).write_text("# Phase 0\n")
        Path(master_file).write_text("# Master\n")

        loop, sm, disp = _make_plan_loop(
            tmp_settings,
            plan_type=PlanType.COMPLEX,
            stage_files=[phase_file, master_file],
            current_stage=1,  # last stage = master
            total_stages=2,
            mock_dir=mock_dir,
        )
        loop.run_review_round(1)

        mock_verify.assert_called_once()
        call_kwargs = mock_verify.call_args
        assert call_kwargs.kwargs.get("check_cross_file") is True
        # Target should be the master file
        assert str(call_kwargs.args[0]) == master_file


# ---------------------------------------------------------------------------
# Test 7.6: plan --init (complex) verifies master with check_cross_file=True
# ---------------------------------------------------------------------------


class TestPlanInitVerifiesMaster:
    """plan --init for complex plan verifies master plan at CLI entry."""

    @patch("orchestrator_v3.cli.verify_plan_syntax")
    def test_plan_init_complex_verifies_master(self, mock_verify, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from orchestrator_v3.cli import app

        runner = CliRunner()
        mock_verify.return_value = _make_failing_result()

        # Set up complex plan structure
        plan_dir = tmp_path / "active_plans" / "test_slug"
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)
        master = plan_dir / "test_slug_master_plan.md"
        master.write_text("# Master Plan\n\n## Phases Overview\n")
        (phases_dir / "phase_0_test.md").write_text("# Phase 0\n\n### [ ] 1 Task\n")
        (tmp_path / "reviews").mkdir()

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        with patch("orchestrator_v3.cli._run_env_preflight"):
            result = runner.invoke(app, [
                "plan", str(master), "--init",
            ])
        assert result.exit_code == 1
        mock_verify.assert_called_once()
        call_kwargs = mock_verify.call_args
        assert call_kwargs.kwargs.get("check_cross_file") is True


# ---------------------------------------------------------------------------
# Test 7.7: code --init verifies master plan
# ---------------------------------------------------------------------------


class TestCodeInitVerifiesMaster:
    """code --init verifies master plan at CLI entry."""

    @patch("orchestrator_v3.cli.verify_plan_syntax")
    def test_code_init_verifies_master(self, mock_verify, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from orchestrator_v3.cli import app

        runner = CliRunner()
        mock_verify.return_value = _make_failing_result()

        # Set up complex plan structure (needs phases/ dir for detect_plan_type)
        plan_dir = tmp_path / "active_plans" / "test_slug"
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)
        master = plan_dir / "test_slug_master_plan.md"
        master.write_text("# Master Plan\n\n## Phases Overview\n")
        (phases_dir / "phase_0_test.md").write_text("# Phase 0\n\n### [ ] 1 Task\n")
        (tmp_path / "reviews").mkdir()

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        with patch("orchestrator_v3.cli._run_env_preflight"):
            result = runner.invoke(app, [
                "code", "test_slug", "0", "1", "--init",
            ])
        # Verify the mock was called — if exit_code is 1 but mock not called,
        # it means the command failed for a different reason
        assert mock_verify.called, (
            f"verify_plan_syntax not called. exit_code={result.exit_code}, "
            f"output={result.output!r}"
        )
        assert result.exit_code == 1
        mock_verify.assert_called_once()
        call_kwargs = mock_verify.call_args
        assert call_kwargs.kwargs.get("check_cross_file") is True


# ---------------------------------------------------------------------------
# Test 7.8: code --resume verifies master plan
# ---------------------------------------------------------------------------


class TestCodeResumeVerifiesMaster:
    """code --resume verifies master plan at CLI entry."""

    @patch("orchestrator_v3.cli.verify_plan_syntax")
    def test_code_resume_verifies_master(self, mock_verify, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from orchestrator_v3.cli import app
        from orchestrator_v3.state import TaskStateManager, task_state_path

        runner = CliRunner()
        mock_verify.return_value = _make_failing_result()

        settings = OrchestratorSettings(repo_root=tmp_path)
        settings.reviews_dir.mkdir(parents=True, exist_ok=True)
        settings.active_plans_dir.mkdir(parents=True, exist_ok=True)

        # Set up plan structure so find_plan_file() works
        plan_dir = settings.active_plans_dir / "test_slug"
        plan_dir.mkdir(parents=True)
        master = plan_dir / "test_slug_master_plan.md"
        master.write_text("# Master Plan\n")

        # Create existing task state (so --resume path is taken)
        ts_path = task_state_path("test_slug", 0, 1, settings)
        tsm = TaskStateManager(state_path=ts_path)
        tsm.init(
            slug="test_slug", phase=0, task=1,
            plan_file=str(master),
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        with patch("orchestrator_v3.cli._run_env_preflight"):
            result = runner.invoke(app, [
                "code", "test_slug", "0", "1", "--resume",
            ])
        assert result.exit_code == 1
        mock_verify.assert_called_once()
        call_kwargs = mock_verify.call_args
        assert call_kwargs.kwargs.get("check_cross_file") is True


# ---------------------------------------------------------------------------
# Test 7.9: Verification failure produces actionable output
# ---------------------------------------------------------------------------


class TestVerificationFailureOutput:
    """Verification failure output includes line numbers and suggestions."""

    def test_verification_failure_actionable_output(self, capsys):
        from orchestrator_v3 import display

        result = _make_failing_result()
        display.print_verification_failure(result)

        captured = capsys.readouterr()
        # Line numbers present
        assert "line 42" in captured.out
        # Error message present
        assert "Task heading malformed" in captured.out
        # Suggestion present
        assert "Suggestion:" in captured.out
        assert "space inside brackets" in captured.out
        # Summary footer
        assert "1 error" in captured.out
        assert "1 warning" in captured.out
        # Header
        assert "PLAN VERIFICATION FAILED" in captured.out


# ---------------------------------------------------------------------------
# Test 7.10: Simple-plan uses check_cross_file=False
# ---------------------------------------------------------------------------


class TestSimplePlanUsesNoCrossFile:
    """Simple-plan round calls verify_plan_syntax with check_cross_file=False."""

    @patch("orchestrator_v3.loop.verify_plan_syntax")
    def test_simple_plan_check_cross_file_false(self, mock_verify, tmp_settings):
        mock_verify.return_value = _make_passing_result()
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        plan_file = str(tmp_settings.active_plans_dir / "simple.md")
        Path(plan_file).write_text("# Simple Plan\n")

        loop, sm, disp = _make_plan_loop(
            tmp_settings,
            plan_type=PlanType.SIMPLE,
            plan_file=plan_file,
            mock_dir=mock_dir,
        )
        loop.run_review_round(1)

        mock_verify.assert_called_once()
        call_kwargs = mock_verify.call_args
        assert call_kwargs.kwargs.get("check_cross_file") is False
        # Target should be the simple plan file
        assert str(call_kwargs.args[0]) == plan_file


# ---------------------------------------------------------------------------
# Test 7.11: Code-mode does NOT call _run_plan_verification
# ---------------------------------------------------------------------------


class TestCodeModeNoVerification:
    """Code-mode run_review_round does NOT call _run_plan_verification."""

    @patch("orchestrator_v3.loop.verify_plan_syntax")
    def test_code_mode_no_plan_verification(self, mock_verify, tmp_settings):
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        loop, sm, disp = _make_code_loop(
            tmp_settings, skip_preflight=True, mock_dir=mock_dir
        )
        # Create code_complete artifact
        loop.artifact_resolver.complete_path(1).write_text("# Code Complete\n")
        outcome = loop.run_review_round(1)

        # verify_plan_syntax should NOT have been called in code mode
        mock_verify.assert_not_called()

    @patch("orchestrator_v3.loop.verify_plan_syntax")
    def test_code_mode_with_preflight_enabled_no_plan_verification(
        self, mock_verify, tmp_settings
    ):
        """Even with skip_preflight=False, code mode should not call plan verification."""
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        loop, sm, disp = _make_code_loop(
            tmp_settings, skip_preflight=False, mock_dir=mock_dir
        )
        # Create code_complete artifact for preflight
        loop.artifact_resolver.complete_path(1).write_text(
            "# Code Complete\n\n"
            "File: path/to/file.py\n\n"
            "~~~diff\n-old\n+new\n~~~\n\n"
            "Test: pytest passes\n\n"
            + "\n".join(f"line {i}" for i in range(50))
        )
        outcome = loop.run_review_round(1)

        # verify_plan_syntax should NOT have been called
        mock_verify.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7.12: Verification warnings don't block
# ---------------------------------------------------------------------------


class TestVerificationWarningsDontBlock:
    """Verification warnings log to stderr but do not block the round."""

    @patch("orchestrator_v3.loop.verify_plan_syntax")
    def test_warnings_dont_block(self, mock_verify, tmp_settings):
        mock_verify.return_value = _make_warning_result()
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir(exist_ok=True)
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        loop, sm, disp = _make_plan_loop(tmp_settings, mock_dir=mock_dir)
        outcome = loop.run_review_round(1)

        # Should NOT be PREFLIGHT_FAILED — warnings only
        assert outcome != ReviewOutcome.PREFLIGHT_FAILED
        # verify_plan_syntax was called
        mock_verify.assert_called_once()
        # print_verification_failure was NOT called (no errors)
        verification_failure_calls = [
            c for c in disp.calls if c[0] == "print_verification_failure"
        ]
        assert len(verification_failure_calls) == 0
