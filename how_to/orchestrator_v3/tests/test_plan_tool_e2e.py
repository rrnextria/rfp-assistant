# Fast: PYTHONPATH=how_to python3.12 -m pytest how_to/orchestrator_v3/tests/test_plan_tool_e2e.py -m "not slow" -v
# Full: PYTHONPATH=how_to python3.12 -m pytest how_to/orchestrator_v3/tests/test_plan_tool_e2e.py -v
"""End-to-End Validation Suite for plan_tool.

Validates the entire plan-tool system works together across all six commands
and the auto-trigger, using real plans as test data.

Test categories:
  1. Real plan round-trip tests (parse, verify, sync, render, re-verify)
  2. Empirical drift repair tests against the triton data corpus
  3. Loop integration E2E tests with mocked orchestration sessions
  4. Regression tests for known defect classes
  5. Error recovery tests under corruption and failure
  6. LLM usability verification checklist (automated measurable criteria)

LLM Usability Checklist (Manual)
================================
After running all tests, manually verify the following:

1. Template instructions visibility:
   - Open each template (phase, master, simple) and verify the plan-verify
     instruction appears within the first 25 lines OR is prominently placed
     in the workflow instructions. Each instruction line includes the full
     CLI command.

2. plan-verify output actionability:
   - Run plan-verify against a plan with 3 injected defects (missing section,
     skipped task number, wrong subtask format). Verify the output includes:
     file path, line number, error description, and a fix suggestion for each
     defect. An LLM should be able to fix all 3 defects from the output alone.

3. plan-verify self-correction:
   - Each error message from (2) includes both a problem description and a
     concrete suggestion field, enabling automated fix without requiring
     model judgment.

4. plan-status output compactness:
   - Run plan-status <slug> --json on a typical campaign (3+ phases).
     Expect output under 800 characters for prompt injection use.

5. plan-show --current output relevance:
   - Run plan-show <slug> --current during a mid-campaign state. Verify the
     output shows only the active task's subtree (not the entire plan), and
     is under 50 lines.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator_v3.approval import Verdict, check_approved, parse_orch_meta
from orchestrator_v3.artifacts import ArtifactResolver
from orchestrator_v3.config import Mode, OrchestratorSettings, PlanType, Status
from orchestrator_v3.loop import OrchestratorLoop, ReviewOutcome
from orchestrator_v3.plan_tool import (
    DriftReport,
    PlanParser,
    ProgressSummary,
    SyncResult,
    parse_plan,
    plan_reconcile,
    plan_render_master,
    plan_show,
    plan_status,
    plan_sync,
    verify_plan_syntax,
)
from orchestrator_v3.reviewer import MockReviewer
from orchestrator_v3.state import (
    CampaignManager,
    TaskStateManager,
    campaign_index_path,
    task_state_path,
)

# ---------------------------------------------------------------------------
# Constants — real data paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TRITON_PLANS = _REPO_ROOT / "research" / "plan_automation" / "empirical_data" / "triton_plans"
_TRITON_REVIEWS = _REPO_ROOT / "research" / "plan_automation" / "empirical_data" / "triton_reviews"
_TEMPLATES_DIR = _REPO_ROOT / "how_to" / "templates"

TRITON_SLUGS = [
    "conda_build_system",
    "gpu_saturation_benchmark",
    "ocr_accuracy_hardening",
    "repo_cleanup_and_testing",
]


# ---------------------------------------------------------------------------
# Task 1: Test Infrastructure & Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def triton_plans_copy(tmp_path):
    """Copy all 4 triton plan directories into tmp_path/active_plans/.

    Each test gets a fresh copy. The active_plans subdirectory matches
    settings.active_plans_dir resolution.
    """
    dest_root = tmp_path / "active_plans"
    for slug in TRITON_SLUGS:
        src = _TRITON_PLANS / slug
        dst = dest_root / slug
        shutil.copytree(src, dst)
    return tmp_path


@pytest.fixture
def triton_reviews_copy(tmp_path):
    """Copy per-task state files and review artifacts from triton_reviews/.

    Preserves the {slug}_p{phase}_t{task}_state.json naming.
    State files live under settings.reviews_dir.
    """
    dest = tmp_path / "reviews"
    dest.mkdir(parents=True, exist_ok=True)
    for f in _TRITON_REVIEWS.iterdir():
        if f.is_file():
            shutil.copy2(f, dest / f.name)
    return dest


@pytest.fixture
def castleguard_copy(tmp_path):
    """Copy TitanAI castleguard plans into tmp_path/active_plans/.

    Skips if TitanAI repo is not available.
    """
    titanai_path = Path("/home/ejkitchen/git/TitanAI/active_plans/castleguard_modernization")
    if not titanai_path.exists():
        pytest.skip("TitanAI repo not available")
    dest = tmp_path / "active_plans" / "castleguard_modernization"
    shutil.copytree(titanai_path, dest)
    return tmp_path


@pytest.fixture
def mock_settings(tmp_path, triton_plans_copy, triton_reviews_copy):
    """OrchestratorSettings with repo_root=tmp_path and triton data copied in."""
    settings = OrchestratorSettings(
        repo_root=tmp_path,
        active_plans_dir=tmp_path / "active_plans",
        reviews_dir=tmp_path / "reviews",
    )
    return settings


@pytest.fixture
def mock_settings_no_reviews(tmp_path, triton_plans_copy):
    """OrchestratorSettings with plans but empty reviews dir."""
    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    return OrchestratorSettings(
        repo_root=tmp_path,
        active_plans_dir=tmp_path / "active_plans",
        reviews_dir=reviews_dir,
    )


# ---------------------------------------------------------------------------
# Task 2: Real Plan Round-Trip Tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Parse, verify, sync, render, and re-verify real triton plans."""

    def test_roundtrip_parse_verify(self, mock_settings_no_reviews):
        """Parse and verify all 4 in-repo triton plans -- parsing succeeds,
        no numbering errors, no depth violations.

        Note: The triton plans pre-date the current template, so they may
        have missing sections (Reviewer Checklist, Completion Step). The
        test verifies structural correctness (numbering, depth, greppable
        patterns) rather than full template compliance.
        """
        settings = mock_settings_no_reviews
        for slug in TRITON_SLUGS:
            plan_dir = settings.active_plans_dir / slug
            phases_dir = plan_dir / "phases"
            assert phases_dir.is_dir(), f"phases/ missing for {slug}"

            # Parse each phase file -- no parse errors, tasks > 0
            for pf in sorted(phases_dir.glob("phase_*.md")):
                parsed = parse_plan(pf, plan_type=PlanType.COMPLEX)
                assert len(parsed.tasks) > 0, f"No tasks parsed in {pf.name}"

            # Verify master plan: check numbering and depth (skip section checks
            # since these legacy plans pre-date the current template)
            master = plan_dir / f"{slug}_master_plan.md"
            result = verify_plan_syntax(
                master,
                settings=settings,
                check_cross_file=False,
                validate_source_paths=False,
            )
            # Filter to numbering and depth errors only (ignore missing-section)
            structural_errors = [
                i for i in result.issues
                if i.severity == "error"
                and "missing required section" not in i.message.lower()
                and "missing required acceptance" not in i.message.lower()
                and "no checkbox items" not in i.message.lower()
            ]
            assert len(structural_errors) == 0, (
                f"Structural errors in {slug}: "
                + "; ".join(i.message for i in structural_errors)
            )

    def test_roundtrip_status(self, mock_settings):
        """Run plan_status on a triton plan, verify ProgressSummary fields."""
        slug = "gpu_saturation_benchmark"
        settings = mock_settings
        summary = plan_status(slug, settings)
        assert isinstance(summary, ProgressSummary)
        assert summary.slug == slug
        assert summary.total_phases == 4  # 4 phase files
        assert summary.total_tasks > 0
        assert len(summary.phase_breakdown) == 4

    def test_roundtrip_sync_single_task(self, mock_settings_no_reviews):
        """Sync a single task, verify checkmark toggled."""
        slug = "gpu_saturation_benchmark"
        settings = mock_settings_no_reviews
        phase_dir = settings.active_plans_dir / slug / "phases"
        phase_file = sorted(phase_dir.glob("phase_0_*.md"))[0]

        # Read original to verify task 1 is unchecked
        original = phase_file.read_text()
        assert "### [ ] 1 " in original

        result = plan_sync(slug, phase=0, task=1, settings=settings)
        assert result.checkmarks_toggled >= 1
        assert result.files_updated == 1

        # Verify the task is now checked
        updated = phase_file.read_text()
        assert "### [\u2705] 1 " in updated

        # Verify other tasks are unchanged
        assert "### [ ] 2 " in updated

    def test_roundtrip_sync_then_render(self, mock_settings_no_reviews):
        """After syncing, render master, verify Phases Overview updated."""
        slug = "gpu_saturation_benchmark"
        settings = mock_settings_no_reviews

        # Sync task 1 in phase 0
        plan_sync(slug, phase=0, task=1, settings=settings)

        # Render master
        render_result = plan_render_master(slug, settings)
        assert render_result.files_updated == 1

        # Read master and verify task 1 is checked in overview
        master = settings.active_plans_dir / slug / f"{slug}_master_plan.md"
        content = master.read_text()
        assert "[\u2705] 1 " in content

    def test_roundtrip_sync_then_verify(self, mock_settings_no_reviews):
        """After sync and render, re-verify plan: no new structural errors."""
        slug = "gpu_saturation_benchmark"
        settings = mock_settings_no_reviews

        # Capture baseline errors before sync
        master = settings.active_plans_dir / slug / f"{slug}_master_plan.md"
        baseline = verify_plan_syntax(
            master, settings=settings, check_cross_file=False, validate_source_paths=False,
        )
        baseline_errors = {i.message for i in baseline.issues if i.severity == "error"}

        plan_sync(slug, phase=0, task=1, settings=settings)
        plan_render_master(slug, settings)

        result = verify_plan_syntax(
            master, settings=settings, check_cross_file=False, validate_source_paths=False,
        )
        new_errors = [
            i for i in result.issues
            if i.severity == "error" and i.message not in baseline_errors
        ]
        assert len(new_errors) == 0, (
            "Sync+render introduced NEW errors: "
            + "; ".join(i.message for i in new_errors)
        )

    def test_roundtrip_full_phase_sync(self, mock_settings_no_reviews):
        """Sync all tasks in a phase, verify all checked."""
        slug = "gpu_saturation_benchmark"
        settings = mock_settings_no_reviews

        # Capture baseline errors
        master = settings.active_plans_dir / slug / f"{slug}_master_plan.md"
        baseline = verify_plan_syntax(
            master, settings=settings, check_cross_file=False, validate_source_paths=False,
        )
        baseline_errors = {i.message for i in baseline.issues if i.severity == "error"}

        # Parse phase 0 to find task count
        phase_dir = settings.active_plans_dir / slug / "phases"
        phase_file = sorted(phase_dir.glob("phase_0_*.md"))[0]
        parsed = parse_plan(phase_file, plan_type=PlanType.COMPLEX)
        top_tasks = [t for t in parsed.tasks if t.level == "top"]

        # Sync all tasks
        for t in top_tasks:
            plan_sync(slug, phase=0, task=int(t.number), settings=settings)

        # Render master
        plan_render_master(slug, settings)

        # Verify all tasks in phase 0 are checked
        updated = phase_file.read_text()
        for t in top_tasks:
            assert f"### [\u2705] {t.number} " in updated

        # Re-verify: no NEW errors introduced
        result = verify_plan_syntax(
            master, settings=settings, check_cross_file=False, validate_source_paths=False,
        )
        new_errors = [
            i for i in result.issues
            if i.severity == "error" and i.message not in baseline_errors
        ]
        assert len(new_errors) == 0, (
            "Full-phase sync introduced NEW errors: "
            + "; ".join(i.message for i in new_errors)
        )


# ---------------------------------------------------------------------------
# Task 3: Empirical Drift Repair Tests
# ---------------------------------------------------------------------------


class TestDriftRepair:
    """Validate plan_reconcile against the real triton data corpus."""

    def test_drift_detection_gpu_saturation(self, mock_settings):
        """Detect drift in gpu_saturation_benchmark."""
        report = plan_reconcile("gpu_saturation_benchmark", mock_settings)
        assert not report.in_sync
        assert len(report.missing_in_plan) > 0
        # Plans have zero checked items, state has approved tasks
        assert len(report.missing_in_state) == 0

    def test_drift_detection_all_triton_plans(self, mock_settings):
        """Detect drift across all 4 triton plans, collect missing_in_plan."""
        all_missing: set[tuple[int, int]] = set()
        for slug in TRITON_SLUGS:
            report = plan_reconcile(slug, mock_settings)
            # Tag each pair with slug info by checking state_completed
            all_missing.update(report.missing_in_plan)

        # The union should contain all approved (phase, task) pairs
        assert len(all_missing) > 0

    def test_drift_count_matches_state_files(self, mock_settings):
        """Drift count matches approved (phase, task) pairs from state."""
        settings = mock_settings
        # Count approved state files
        approved_count = 0
        state_re = re.compile(r"^(.+)_p(\d+)_t(\d+)_state\.json$")
        for f in settings.reviews_dir.iterdir():
            m = state_re.match(f.name)
            if m:
                slug_from_file = m.group(1)
                if slug_from_file in TRITON_SLUGS:
                    data = json.loads(f.read_text())
                    if data.get("status") in ("approved", "complete"):
                        approved_count += 1

        # Sum missing_in_plan across all slugs
        total_missing = 0
        for slug in TRITON_SLUGS:
            report = plan_reconcile(slug, settings)
            total_missing += len(report.missing_in_plan)

        assert total_missing == approved_count

    def test_drift_apply_fixes_all(self, mock_settings):
        """Apply fixes, re-check drift -- in_sync=True."""
        settings = mock_settings
        for slug in TRITON_SLUGS:
            plan_reconcile(slug, settings, apply=True)

        # Re-check: all should be in sync
        for slug in TRITON_SLUGS:
            report = plan_reconcile(slug, settings)
            assert report.in_sync, (
                f"{slug} still has drift after apply: "
                f"missing_in_plan={report.missing_in_plan}, "
                f"missing_in_state={report.missing_in_state}"
            )

    def test_drift_apply_preserves_structure(self, mock_settings):
        """After apply, verify no new structural errors introduced."""
        settings = mock_settings

        # Capture baseline errors for each plan
        baselines: dict[str, set[str]] = {}
        for slug in TRITON_SLUGS:
            master = settings.active_plans_dir / slug / f"{slug}_master_plan.md"
            result = verify_plan_syntax(
                master, settings=settings, check_cross_file=False,
                validate_source_paths=False,
            )
            baselines[slug] = {i.message for i in result.issues if i.severity == "error"}

        # Apply drift fixes
        for slug in TRITON_SLUGS:
            plan_reconcile(slug, settings, apply=True)

        # Verify no NEW errors introduced by apply
        for slug in TRITON_SLUGS:
            master = settings.active_plans_dir / slug / f"{slug}_master_plan.md"
            result = verify_plan_syntax(
                master, settings=settings, check_cross_file=False,
                validate_source_paths=False,
            )
            new_errors = [
                i for i in result.issues
                if i.severity == "error" and i.message not in baselines[slug]
            ]
            assert len(new_errors) == 0, (
                f"Apply introduced NEW errors in {slug}: "
                + "; ".join(i.message for i in new_errors)
            )

    def test_drift_from_reviews(self, mock_settings):
        """from_reviews=True is superset of state-file-only reconciliation."""
        settings = mock_settings
        for slug in TRITON_SLUGS:
            report_state = plan_reconcile(slug, settings, from_reviews=False)
            report_reviews = plan_reconcile(slug, settings, from_reviews=True)
            # from_reviews should find at least as many completed tasks
            assert report_reviews.state_completed >= report_state.state_completed, (
                f"{slug}: from_reviews found {len(report_reviews.state_completed)} "
                f"but state-only found {len(report_state.state_completed)}"
            )


# ---------------------------------------------------------------------------
# Task 4: Loop Integration E2E Tests
# ---------------------------------------------------------------------------


def _make_approved_review(path: Path) -> None:
    """Write a valid APPROVED ORCH_META review file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<!-- ORCH_META\n"
        "VERDICT: APPROVED\n"
        "BLOCKER: 0\n"
        "MAJOR: 0\n"
        "MINOR: 0\n"
        "DECISIONS: 0\n"
        "VERIFIED: 1\n"
        "-->\n\n"
        "# Review\n\nLooks good.\n"
    )


def _setup_code_mode_loop(tmp_path, slug="test_e2e", plan_type=PlanType.COMPLEX):
    """Set up a complete code-mode loop environment.

    Returns (loop, settings, phase_file, master_file, cm, tsm, ar).
    """
    # Create directory structure
    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    plans_dir = tmp_path / "active_plans"
    plan_dir = plans_dir / slug
    phases_dir = plan_dir / "phases"
    phases_dir.mkdir(parents=True, exist_ok=True)

    settings = OrchestratorSettings(
        repo_root=tmp_path,
        active_plans_dir=plans_dir,
        reviews_dir=reviews_dir,
    )

    if plan_type == PlanType.COMPLEX:
        # Create master plan
        master_file = plan_dir / f"{slug}_master_plan.md"
        master_file.write_text(
            f"# {slug} Master Plan\n\n"
            "## Executive Summary\nTest plan.\n\n"
            "## Detailed Objective\nTest.\n\n"
            "## Quick Navigation\n| Phase | File |\n\n"
            "## Architecture Overview\nN/A\n\n"
            "## Current State\nNone.\n\n"
            "## Desired State\nDone.\n\n"
            "## Global Risks & Mitigations\nNone.\n\n"
            "## Global Acceptance Gates\n- [ ] Gate 1: All tests pass\n\n"
            "## Dependency Gates\n- [ ] None\n\n"
            "## Phases Overview\n\n"
            "### Phase 0: Test Phase\n\n"
            "#### Tasks\n\n"
            "### [ ] 1 Task One\n"
            "  - [ ] 1.1 Subtask\n\n"
            "## Decision Log\n- D1: Test\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )

        # Create phase file
        phase_file = phases_dir / "phase_0_test.md"
        phase_file.write_text(
            "# Phase 0: Test Phase\n\n"
            "**Status:** Pending\n\n---\n\n"
            "## Detailed Objective\nTest objective.\n\n"
            "## Deliverables Snapshot\n1. Test deliverable\n\n"
            "## Acceptance Gates\n- [ ] Gate 1: Test passes\n\n"
            "## Scope\n- In scope: everything\n\n"
            "## Interfaces & Dependencies\n- None\n\n"
            "## Risks & Mitigations\nNone.\n\n"
            "## Decision Log\n- D1: Test\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Tasks\n\n"
            "### [ ] 1 Task One\nDo the thing.\n\n"
            "  - [ ] 1.1 Subtask A\n"
            "  - [ ] 1.2 Subtask B\n\n"
            "## Completion Step (Required)\nRun tests.\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )
        plan_file_str = str(master_file)
    else:
        # Simple plan
        simple_file = plans_dir / f"{slug}.md"
        simple_file.write_text(
            f"# {slug}\n\n"
            "## Objective\nTest.\n\n"
            "## Current vs Desired\nNone -> Done.\n\n"
            "## Scope\n- Everything\n\n"
            "## Policies & Contracts\nNone.\n\n"
            "## Tasks\n\n"
            "### [ ] 1 Task One\n#### [ ] 1.1 Sub One\n\n"
            "## Acceptance Criteria\n- [ ] Tests pass\n\n"
            "## Risks & Mitigations\nNone.\n\n"
            "## Validation\nRun tests.\n\n"
            "## Artifacts Created\nNone.\n\n"
            "## Interfaces & Dependencies\nNone.\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )
        plan_file_str = str(simple_file)
        phase_file = simple_file
        master_file = simple_file

    # Set up per-task state
    ts_path = task_state_path(slug, 0, 1, settings)
    tsm = TaskStateManager(state_path=ts_path)
    tsm.init(slug=slug, phase=0, task=1, plan_file=plan_file_str, mode=Mode.CODE)

    # Set up campaign manager
    ci_path = campaign_index_path(slug, settings)
    cm = CampaignManager(state_path=ci_path, settings=settings)
    cm.init(
        slug=slug,
        mode=Mode.CODE,
        plan_file=plan_file_str,
        total_phases=1,
        tasks_per_phase={"0": 1},
        current_phase=0,
        current_task=1,
    )

    # Set up artifact resolver
    ar = ArtifactResolver(
        slug=slug, mode=Mode.CODE, phase=0, task=1, settings=settings
    )

    # Create code_complete artifact
    complete_path = ar.complete_path(1)
    complete_path.parent.mkdir(parents=True, exist_ok=True)
    complete_path.write_text("# Code Complete Round 1\n\nAll work done.\n")

    # Set up mock reviewer
    mock_dir = tmp_path / "mock_reviews"
    mock_dir.mkdir(parents=True, exist_ok=True)
    _make_approved_review(mock_dir / "round1_review.md")
    reviewer = MockReviewer(mock_dir)

    # Create a stub prompt builder
    prompt_builder = MagicMock()
    prompt_builder.build_code_prompt.return_value = "Review this code."

    # Create a stub display
    display = MagicMock()

    # Create the loop
    loop = OrchestratorLoop(
        state_manager=tsm,
        artifact_resolver=ar,
        prompt_builder=prompt_builder,
        reviewer=reviewer,
        display=display,
        settings=settings,
        campaign_manager=cm,
        skip_preflight=True,
    )

    return loop, settings, phase_file, master_file, cm, tsm, ar


class TestLoopIntegration:
    """Loop integration E2E tests with Mode.CODE + MockReviewer."""

    def test_approval_cycle_e2e_via_loop(self, tmp_path):
        """Full loop path: run_review_round -> APPROVED -> handle_approval."""
        loop, settings, phase_file, master_file, cm, tsm, ar = _setup_code_mode_loop(tmp_path)

        # Run a review round
        outcome = loop.run_review_round(1)
        assert outcome == ReviewOutcome.APPROVED

        # Verify review artifact exists and is approved
        review_file = ar.review_path(1)
        assert review_file.exists()
        assert check_approved(review_file)

        # Handle approval
        loop.handle_approval(1)

        # Verify campaign advanced
        ci = cm.load()
        assert ci.status in ("complete", "needs_review")

        # Verify plan sync happened (task 1 should be checked)
        updated = phase_file.read_text()
        assert "[\u2705] 1 " in updated

    def test_auto_trigger_fires_on_approval(self, tmp_path):
        """Verify plan_sync called after approval."""
        loop, settings, phase_file, master_file, cm, tsm, ar = _setup_code_mode_loop(tmp_path)

        # Write the review artifact manually
        review_file = ar.review_path(1)
        _make_approved_review(review_file)

        # Handle approval directly
        loop.handle_approval(1)

        # Verify phase file has checkmark
        updated = phase_file.read_text()
        assert "### [\u2705] 1 " in updated

    def test_auto_trigger_renders_master_for_complex(self, tmp_path):
        """Verify plan_render_master called for complex plan."""
        loop, settings, phase_file, master_file, cm, tsm, ar = _setup_code_mode_loop(
            tmp_path, plan_type=PlanType.COMPLEX
        )

        review_file = ar.review_path(1)
        _make_approved_review(review_file)

        loop.handle_approval(1)

        # Master plan should reflect the synced checkmark
        content = master_file.read_text()
        assert "[\u2705] 1 " in content

    def test_auto_trigger_skips_sync_for_simple(self, tmp_path):
        """Simple plan -> no sync/render via auto-trigger."""
        loop, settings, phase_file, master_file, cm, tsm, ar = _setup_code_mode_loop(
            tmp_path, slug="simple_e2e", plan_type=PlanType.SIMPLE
        )

        review_file = ar.review_path(1)
        _make_approved_review(review_file)

        # Read original content
        original = phase_file.read_text()

        loop.handle_approval(1)

        # Simple plan file should NOT have been modified by auto-trigger
        # (detect_plan_type returns SIMPLE, so the auto-trigger branch skips)
        updated = phase_file.read_text()
        assert updated == original

    def test_auto_trigger_nonfatal_on_sync_error(self, tmp_path):
        """Sync error doesn't propagate -- handle_approval completes."""
        loop, settings, phase_file, master_file, cm, tsm, ar = _setup_code_mode_loop(tmp_path)

        review_file = ar.review_path(1)
        _make_approved_review(review_file)

        with patch("orchestrator_v3.plan_tool.plan_sync", side_effect=RuntimeError("boom")):
            # Should not raise
            loop.handle_approval(1)

        # Campaign should still have advanced
        ci = cm.load()
        assert ci.status in ("complete", "needs_review")

    def test_auto_trigger_nonfatal_on_render_error(self, tmp_path):
        """Render error doesn't propagate -- handle_approval completes."""
        loop, settings, phase_file, master_file, cm, tsm, ar = _setup_code_mode_loop(tmp_path)

        review_file = ar.review_path(1)
        _make_approved_review(review_file)

        with patch("orchestrator_v3.plan_tool.plan_render_master", side_effect=OSError("disk full")):
            loop.handle_approval(1)

        ci = cm.load()
        assert ci.status in ("complete", "needs_review")

    def test_status_reflects_approval(self, tmp_path):
        """After approval, plan_status shows updated count."""
        loop, settings, phase_file, master_file, cm, tsm, ar = _setup_code_mode_loop(tmp_path)
        slug = "test_e2e"

        # Before approval: no tasks completed
        pre_status = plan_status(slug, settings)
        assert pre_status.total_completed == 0

        # Perform approval
        review_file = ar.review_path(1)
        _make_approved_review(review_file)
        loop.handle_approval(1)

        # After approval: task should be completed
        post_status = plan_status(slug, settings)
        assert post_status.total_completed >= 1


# ---------------------------------------------------------------------------
# Task 5: Regression Tests
# ---------------------------------------------------------------------------


class TestRegression:
    """Confirm all known defect classes are handled correctly."""

    def test_checkmark_variants_in_count(self, tmp_path):
        """plan_status and parser count both [x] and checkmark as completed."""
        plans_dir = tmp_path / "active_plans" / "cktest"
        phases_dir = plans_dir / "phases"
        phases_dir.mkdir(parents=True)

        master = plans_dir / "cktest_master_plan.md"
        master.write_text(
            "# cktest Master Plan\n\n"
            "## Executive Summary\nTest.\n\n"
            "## Detailed Objective\nTest.\n\n"
            "## Quick Navigation\nN/A\n\n"
            "## Architecture Overview\nN/A\n\n"
            "## Current State\nNone.\n\n"
            "## Desired State\nDone.\n\n"
            "## Global Risks & Mitigations\nNone.\n\n"
            "## Global Acceptance Gates\n- [ ] Gate 1\n\n"
            "## Dependency Gates\n- None\n\n"
            "## Phases Overview\n\n"
            "### Phase 0: Test\n\n"
            "### [x] 1 Done via x\n"
            "### [\u2705] 2 Done via checkmark\n"
            "### [ ] 3 Not done\n\n"
            "## Decision Log\nNone.\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )

        phase = phases_dir / "phase_0_test.md"
        phase.write_text(
            "# Phase 0: Test\n\n**Status:** Active\n\n---\n\n"
            "## Detailed Objective\nTest.\n\n"
            "## Deliverables Snapshot\n1. Test\n\n"
            "## Acceptance Gates\n- [ ] Gate 1\n\n"
            "## Scope\n- Everything\n\n"
            "## Interfaces & Dependencies\nNone.\n\n"
            "## Risks & Mitigations\nNone.\n\n"
            "## Decision Log\nNone.\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Tasks\n\n"
            "### [x] 1 Done via x\nDescription.\n\n"
            "### [\u2705] 2 Done via checkmark\nDescription.\n\n"
            "### [ ] 3 Not done\nDescription.\n\n"
            "## Completion Step (Required)\nRun tests.\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )

        parsed = parse_plan(phase, plan_type=PlanType.COMPLEX)
        top_tasks = [t for t in parsed.tasks if t.level == "top"]
        checked = [t for t in top_tasks if t.checked]
        assert len(checked) == 2, f"Expected 2 checked tasks, got {len(checked)}"

    def test_parser_handles_all_template_types(self, tmp_path):
        """Parse phase, master, and simple plans -- correct types."""
        # Phase plan (inside a phases/ directory)
        complex_dir = tmp_path / "complex"
        phases_dir = complex_dir / "phases"
        phases_dir.mkdir(parents=True)
        phase = phases_dir / "phase_0_test.md"
        phase.write_text(
            "# Phase 0: Test\n\n## Tasks\n\n"
            "### [ ] 1 Task One\nDo thing.\n\n"
            "  - [ ] 1.1 Sub\n\n"
            "## Completion Step (Required)\nDone.\n"
        )
        parsed_phase = parse_plan(phase)
        assert parsed_phase.plan_type == PlanType.COMPLEX
        assert len(parsed_phase.tasks) >= 1

        # Master plan (parent has phases/ directory)
        master = complex_dir / "test_master_plan.md"
        master.write_text(
            "# Master Plan\n\n## Phases Overview\n\n"
            "### Phase 0: Test\n\n"
            "### [ ] 1 Task\n\n"
        )
        parsed_master = parse_plan(master)
        assert parsed_master.plan_type == PlanType.COMPLEX

        # Simple plan (separate directory, no phases/ subdir)
        simple_dir = tmp_path / "simple_dir"
        simple_dir.mkdir()
        simple = simple_dir / "simple.md"
        simple.write_text(
            "# Simple Plan\n\n## Tasks\n\n"
            "### [ ] 1 Task\n\n"
            "#### [ ] 1.1 Sub\n\n"
        )
        parsed_simple = parse_plan(simple)
        assert parsed_simple.plan_type == PlanType.SIMPLE

    def test_verify_catches_skipped_numbers(self, tmp_path):
        """Numbering gap detection."""
        phase_dir = tmp_path / "phases"
        phase_dir.mkdir()
        phase = phase_dir / "phase_0_test.md"
        phase.write_text(
            "# Phase 0: Test\n\n**Status:** Pending\n\n---\n\n"
            "## Detailed Objective\nTest.\n\n"
            "## Deliverables Snapshot\n1. Test\n\n"
            "## Acceptance Gates\n- [ ] Gate 1\n\n"
            "## Scope\n- Everything\n\n"
            "## Interfaces & Dependencies\nNone.\n\n"
            "## Risks & Mitigations\nNone.\n\n"
            "## Decision Log\nNone.\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Tasks\n\n"
            "### [ ] 1 First\nDo first.\n\n"
            "### [ ] 2 Second\nDo second.\n\n"
            "### [ ] 4 Fourth\nDo fourth -- skip 3.\n\n"
            "## Completion Step (Required)\nDone.\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )
        result = verify_plan_syntax(phase, check_cross_file=False, validate_source_paths=False)
        numbering_errors = [
            i for i in result.issues
            if i.severity == "error" and "missing" in i.message.lower()
        ]
        assert len(numbering_errors) >= 1, "Should detect numbering gap"

    def test_verify_catches_missing_sections(self, tmp_path):
        """Missing section detection."""
        phase_dir = tmp_path / "phases"
        phase_dir.mkdir()
        phase = phase_dir / "phase_0_test.md"
        # Missing Acceptance Gates section
        phase.write_text(
            "# Phase 0: Test\n\n**Status:** Pending\n\n---\n\n"
            "## Detailed Objective\nTest.\n\n"
            "## Deliverables Snapshot\n1. Test\n\n"
            "## Scope\n- Everything\n\n"
            "## Interfaces & Dependencies\nNone.\n\n"
            "## Risks & Mitigations\nNone.\n\n"
            "## Decision Log\nNone.\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Tasks\n\n"
            "### [ ] 1 Task\nDo it.\n\n"
            "## Completion Step (Required)\nDone.\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )
        result = verify_plan_syntax(phase, check_cross_file=False, validate_source_paths=False)
        missing_errors = [
            i for i in result.issues
            if i.severity == "error" and "missing" in i.message.lower() and "acceptance" in i.message.lower()
        ]
        assert len(missing_errors) >= 1, "Should detect missing Acceptance Gates"

    def test_verify_catches_wrong_subtask_format(self, tmp_path):
        """Wrong subtask grammar detection in simple plan."""
        simple = tmp_path / "wrong_format.md"
        simple.write_text(
            "# Wrong Format Plan\n\n"
            "## Objective\nTest.\n\n"
            "## Current vs Desired\nNone -> Done.\n\n"
            "## Scope\n- Everything\n\n"
            "## Policies & Contracts\nNone.\n\n"
            "## Tasks\n\n"
            "### [ ] 1 Task One\n"
            "  - [ ] 1.1 Subtask should be ####\n\n"
            "## Acceptance Criteria\n- [ ] Pass\n\n"
            "## Risks & Mitigations\nNone.\n\n"
            "## Validation\nRun tests.\n\n"
            "## Artifacts Created\nNone.\n\n"
            "## Interfaces & Dependencies\nNone.\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )
        result = verify_plan_syntax(simple, check_cross_file=False, validate_source_paths=False)
        format_errors = [
            i for i in result.issues
            if i.severity == "error" and "bullet" in i.message.lower()
        ]
        assert len(format_errors) >= 1, "Should detect wrong subtask format"

    def test_sync_idempotent_repeated(self, tmp_path):
        """Multiple syncs = same result."""
        slug = "idem_test"
        plans_dir = tmp_path / "active_plans" / slug / "phases"
        plans_dir.mkdir(parents=True)
        phase = plans_dir / "phase_0_test.md"
        phase.write_text(
            "# Phase 0: Test\n\n## Tasks\n\n"
            "### [ ] 1 Task One\nDo it.\n\n"
            "  - [ ] 1.1 Sub\n\n"
        )
        settings = OrchestratorSettings(
            repo_root=tmp_path,
            active_plans_dir=tmp_path / "active_plans",
            reviews_dir=tmp_path / "reviews",
        )
        (tmp_path / "reviews").mkdir(exist_ok=True)

        # First sync
        r1 = plan_sync(slug, phase=0, task=1, settings=settings)
        assert r1.checkmarks_toggled >= 1
        content_after_first = phase.read_text()

        # Second sync (idempotent)
        r2 = plan_sync(slug, phase=0, task=1, settings=settings)
        assert r2.checkmarks_toggled == 0

        # Third sync
        r3 = plan_sync(slug, phase=0, task=1, settings=settings)
        assert r3.checkmarks_toggled == 0

        # Content unchanged after first sync
        assert phase.read_text() == content_after_first

    def test_cross_file_check_scoping(self, tmp_path):
        """Phase-stage skips cross-file, master-stage includes it."""
        slug = "xfile"
        plan_dir = tmp_path / "active_plans" / slug
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)

        settings = OrchestratorSettings(
            repo_root=tmp_path,
            active_plans_dir=tmp_path / "active_plans",
            reviews_dir=tmp_path / "reviews",
        )
        (tmp_path / "reviews").mkdir(exist_ok=True)

        # Create master with 1 task, phase with 2 tasks (mismatch)
        master = plan_dir / f"{slug}_master_plan.md"
        master.write_text(
            "# xfile Master Plan\n\n"
            "## Executive Summary\nTest.\n\n"
            "## Detailed Objective\nTest.\n\n"
            "## Quick Navigation\nN/A\n\n"
            "## Architecture Overview\nN/A\n\n"
            "## Current State\nNone.\n\n"
            "## Desired State\nDone.\n\n"
            "## Global Risks & Mitigations\nNone.\n\n"
            "## Global Acceptance Gates\n- [ ] Gate 1\n\n"
            "## Dependency Gates\n- None\n\n"
            "## Phases Overview\n\n"
            "### Phase 0: Test\n\n"
            "### [ ] 1 Task One\n\n"
            "## Decision Log\nNone.\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )

        phase = phases_dir / "phase_0_test.md"
        phase.write_text(
            "# Phase 0: Test\n\n**Status:** Pending\n\n---\n\n"
            "## Detailed Objective\nTest.\n\n"
            "## Deliverables Snapshot\n1. Test\n\n"
            "## Acceptance Gates\n- [ ] Gate 1\n\n"
            "## Scope\n- Everything\n\n"
            "## Interfaces & Dependencies\nNone.\n\n"
            "## Risks & Mitigations\nNone.\n\n"
            "## Decision Log\nNone.\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Tasks\n\n"
            "### [ ] 1 Task One\nDo it.\n\n"
            "### [ ] 2 Task Two\nDo more.\n\n"
            "## Completion Step (Required)\nDone.\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )

        # Phase file without cross-file: no mismatch errors
        result_no_xf = verify_plan_syntax(
            phase, settings=settings, check_cross_file=False, validate_source_paths=False
        )
        xf_errors_no = [
            i for i in result_no_xf.issues
            if i.severity == "error" and "task" in i.message.lower() and "mismatch" in i.message.lower()
        ]
        assert len(xf_errors_no) == 0

        # Master with cross-file: should detect mismatch
        result_xf = verify_plan_syntax(
            master, settings=settings, check_cross_file=True, validate_source_paths=False
        )
        xf_errors = [
            i for i in result_xf.issues
            if i.severity == "error" and ("master has" in i.message.lower() or "mismatch" in i.message.lower())
        ]
        assert len(xf_errors) >= 1, "Should detect cross-file task count mismatch"


# ---------------------------------------------------------------------------
# Task 6: Error Recovery Tests
# ---------------------------------------------------------------------------


class TestErrorRecovery:
    """Verify graceful degradation under corruption and failure."""

    def test_corrupted_state_file_reconcile(self, tmp_path):
        """Handles corrupt JSON gracefully."""
        slug = "corrupt_test"
        plans_dir = tmp_path / "active_plans" / slug / "phases"
        plans_dir.mkdir(parents=True)
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()

        # Create a valid phase file
        phase = plans_dir / "phase_0_test.md"
        phase.write_text(
            "# Phase 0: Test\n\n## Tasks\n\n"
            "### [ ] 1 Task One\nDo it.\n\n"
        )

        # Create master plan
        master = plans_dir.parent / f"{slug}_master_plan.md"
        master.write_text(
            f"# {slug} Master Plan\n\n## Phases Overview\n\n"
            "### Phase 0: Test\n\n### [ ] 1 Task One\n\n"
        )

        # Create corrupt state file
        corrupt_state = reviews_dir / f"{slug}_p0_t1_state.json"
        corrupt_state.write_text("{{{not valid json!!!")

        # Create a valid state file too
        valid_state = reviews_dir / f"{slug}_p0_t2_state.json"
        valid_state.write_text(json.dumps({
            "slug": slug, "phase": 0, "task": 2, "mode": "code",
            "current_round": 1, "status": "approved", "plan_file": "",
            "code_artifact_hash": None, "started_at": "", "last_updated": "",
            "history": [],
        }))

        settings = OrchestratorSettings(
            repo_root=tmp_path,
            active_plans_dir=tmp_path / "active_plans",
            reviews_dir=reviews_dir,
        )

        # Should not crash -- skips corrupted file
        report = plan_reconcile(slug, settings)
        assert isinstance(report, DriftReport)

    def test_missing_phase_file_reconcile(self, mock_settings):
        """Handles missing phase file during reconcile."""
        settings = mock_settings
        slug = "gpu_saturation_benchmark"

        # Delete one phase file
        phases_dir = settings.active_plans_dir / slug / "phases"
        phase_files = sorted(phases_dir.glob("phase_*.md"))
        assert len(phase_files) > 1
        phase_files[0].unlink()

        # Reconcile should still work (processes remaining phases)
        report = plan_reconcile(slug, settings)
        assert isinstance(report, DriftReport)

    def test_missing_master_plan_render(self, tmp_path):
        """Handles missing master plan with FileNotFoundError."""
        slug = "no_master"
        plans_dir = tmp_path / "active_plans" / slug / "phases"
        plans_dir.mkdir(parents=True)
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()

        phase = plans_dir / "phase_0_test.md"
        phase.write_text("# Phase 0: Test\n\n### [ ] 1 Task\n")

        settings = OrchestratorSettings(
            repo_root=tmp_path,
            active_plans_dir=tmp_path / "active_plans",
            reviews_dir=reviews_dir,
        )

        with pytest.raises(FileNotFoundError):
            plan_render_master(slug, settings)

    def test_empty_phase_file_parse(self, tmp_path):
        """Handles empty file -- returns ParsedPlan with zero tasks."""
        phase_dir = tmp_path / "phases"
        phase_dir.mkdir()
        phase = phase_dir / "phase_0_empty.md"
        phase.write_text("# Phase 0: Empty\n")

        parsed = parse_plan(phase, plan_type=PlanType.COMPLEX)
        assert len(parsed.tasks) == 0

    def test_sync_nonexistent_task(self, tmp_path):
        """ValueError for missing task."""
        slug = "notask"
        plans_dir = tmp_path / "active_plans" / slug / "phases"
        plans_dir.mkdir(parents=True)
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()

        phase = plans_dir / "phase_0_test.md"
        phase.write_text(
            "# Phase 0: Test\n\n## Tasks\n\n"
            "### [ ] 1 Task One\nDo it.\n\n"
        )

        settings = OrchestratorSettings(
            repo_root=tmp_path,
            active_plans_dir=tmp_path / "active_plans",
            reviews_dir=reviews_dir,
        )

        with pytest.raises(ValueError, match="99"):
            plan_sync(slug, phase=0, task=99, settings=settings)

    def test_sync_during_approval_failure_recovery(self, tmp_path):
        """advance_task() succeeds, then sync failure doesn't roll back state."""
        loop, settings, phase_file, master_file, cm, tsm, ar = _setup_code_mode_loop(tmp_path)

        review_file = ar.review_path(1)
        _make_approved_review(review_file)

        # Mock plan_sync to fail (patched at source module where it's imported from)
        with patch("orchestrator_v3.plan_tool.plan_sync", side_effect=RuntimeError("sync failed")):
            loop.handle_approval(1)

        # Campaign state should still reflect advancement
        ci = cm.load()
        assert ci.status in ("complete", "needs_review")

        # Per-task state should be approved
        ts = tsm.load()
        assert ts.status in ("approved",)

    def test_half_written_plan_file(self, tmp_path):
        """Handles truncated file -- parses what it can, no crash."""
        phase_dir = tmp_path / "phases"
        phase_dir.mkdir()
        phase = phase_dir / "phase_0_truncated.md"
        # Truncated mid-task: heading present but content cut off
        phase.write_text(
            "# Phase 0: Truncated\n\n## Tasks\n\n"
            "### [ ] 1 Task One\nStart of description\n"
            "  - [ ] 1.1 Sub"  # No newline, truncated
        )

        parsed = parse_plan(phase, plan_type=PlanType.COMPLEX)
        # Should parse at least the top-level task
        assert len(parsed.tasks) >= 1
        assert parsed.tasks[0].number == "1"


# ---------------------------------------------------------------------------
# Task 7: LLM Usability Verification Checklist
# ---------------------------------------------------------------------------


class TestLLMUsability:
    """Automated measurable criteria from the LLM usability checklist."""

    def test_template_instructions_contain_plan_verify(self):
        """Each template contains a plan-verify CLI command."""
        templates = [
            _TEMPLATES_DIR / "phase_plan_template.md",
            _TEMPLATES_DIR / "master_plan_template.md",
            _TEMPLATES_DIR / "simple_plan_template.md",
        ]
        for tpl in templates:
            assert tpl.exists(), f"Template not found: {tpl}"
            content = tpl.read_text()
            assert "plan-verify" in content, (
                f"Template {tpl.name} does not contain 'plan-verify' instruction"
            )

    def test_verify_output_includes_actionable_fields(self, tmp_path):
        """plan-verify output includes file path, line number, description, suggestion."""
        # Create a plan with 3 injected defects
        phase_dir = tmp_path / "phases"
        phase_dir.mkdir()
        phase = phase_dir / "phase_0_defects.md"
        phase.write_text(
            "# Phase 0: Defects\n\n**Status:** Pending\n\n---\n\n"
            "## Detailed Objective\nTest.\n\n"
            "## Deliverables Snapshot\n1. Test\n\n"
            # Missing Acceptance Gates section (defect 1)
            "## Scope\n- Everything\n\n"
            "## Interfaces & Dependencies\nNone.\n\n"
            "## Risks & Mitigations\nNone.\n\n"
            "## Decision Log\nNone.\n\n"
            "## References\n### Source Files\n- None\n"
            "### Destination Files\n- None\n"
            "### Related Documentation\n- None\n\n"
            "## Tasks\n\n"
            "### [ ] 1 First Task\nDo first.\n\n"
            # Skipped task number (defect 2)
            "### [ ] 3 Third Task\nDo third.\n\n"
            "## Completion Step (Required)\nDone.\n\n"
            "## Reviewer Checklist\n- [ ] Done\n"
        )

        result = verify_plan_syntax(phase, check_cross_file=False, validate_source_paths=False)
        assert not result.passed
        assert len(result.issues) >= 2

        # Each error should have a line_number, message, and suggestion
        for issue in result.issues:
            if issue.severity == "error":
                assert issue.line_number is not None, (
                    f"Error missing line_number: {issue.message}"
                )
                assert len(issue.message) > 0, "Error missing message"
                assert issue.suggestion is not None and len(issue.suggestion) > 0, (
                    f"Error missing suggestion: {issue.message}"
                )

    def test_plan_status_output_under_800_chars(self, tmp_path):
        """plan-status JSON output should be compact (<800 chars)."""
        slug = "compact_test"
        plans_dir = tmp_path / "active_plans" / slug / "phases"
        plans_dir.mkdir(parents=True)
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()

        # Create a 3-phase plan
        master = plans_dir.parent / f"{slug}_master_plan.md"
        master.write_text(
            f"# {slug} Master Plan\n\n## Phases Overview\n\n"
            "### Phase 0: Setup\n### [ ] 1 T1\n### [ ] 2 T2\n\n"
            "### Phase 1: Build\n### [ ] 1 T1\n### [ ] 2 T2\n### [ ] 3 T3\n\n"
            "### Phase 2: Deploy\n### [ ] 1 T1\n### [ ] 2 T2\n\n"
        )

        for i, (name, tasks) in enumerate([
            ("setup", 2), ("build", 3), ("deploy", 2),
        ]):
            phase = plans_dir / f"phase_{i}_{name}.md"
            lines = [f"# Phase {i}: {name.title()}\n\n## Tasks\n\n"]
            for t in range(1, tasks + 1):
                lines.append(f"### [ ] {t} Task {t}\nDo {t}.\n\n")
            phase.write_text("".join(lines))

        settings = OrchestratorSettings(
            repo_root=tmp_path,
            active_plans_dir=tmp_path / "active_plans",
            reviews_dir=reviews_dir,
        )

        summary = plan_status(slug, settings)
        json_output = json.dumps(summary.to_json())
        assert len(json_output) < 800, (
            f"plan-status JSON is {len(json_output)} chars (expected <800)"
        )

    def test_plan_show_current_output_relevant(self, tmp_path):
        """plan-show --current shows only active task subtree."""
        slug = "show_test"
        plans_dir = tmp_path / "active_plans" / slug / "phases"
        plans_dir.mkdir(parents=True)
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()

        master = plans_dir.parent / f"{slug}_master_plan.md"
        master.write_text(
            f"# {slug} Master Plan\n\n## Phases Overview\n\n"
            "### Phase 0: Work\n\n### [ ] 1 T1\n### [ ] 2 T2\n\n"
        )

        phase = plans_dir / "phase_0_work.md"
        phase.write_text(
            "# Phase 0: Work\n\n## Tasks\n\n"
            "### [ ] 1 Task One\nDo the first thing.\n\n"
            "  - [ ] 1.1 Sub A\n  - [ ] 1.2 Sub B\n\n"
            "### [ ] 2 Task Two\nDo the second thing.\n\n"
            "  - [ ] 2.1 Sub C\n"
        )

        settings = OrchestratorSettings(
            repo_root=tmp_path,
            active_plans_dir=tmp_path / "active_plans",
            reviews_dir=reviews_dir,
        )

        # Create campaign state at phase 0, task 1
        ci_path = campaign_index_path(slug, settings)
        cm = CampaignManager(state_path=ci_path, settings=settings)
        cm.init(
            slug=slug, mode=Mode.CODE, plan_file=str(master),
            total_phases=1, tasks_per_phase={"0": 2},
            current_phase=0, current_task=1,
        )

        output = plan_show(slug, settings, current=True)
        lines = output.strip().split("\n")
        assert len(lines) < 50, f"plan-show --current output is {len(lines)} lines (expected <50)"
        # Should contain Task 1 content
        assert "Task One" in output or "1 " in output


# ---------------------------------------------------------------------------
# Task 8: Slow tests (model API calls / TitanAI access)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestCastleguard:
    """Tests requiring TitanAI repo access."""

    def test_castleguard_parse_verify(self, castleguard_copy):
        """Parse and verify TitanAI castleguard plans."""
        tmp_path = castleguard_copy
        plan_dir = tmp_path / "active_plans" / "castleguard_modernization"
        phases_dir = plan_dir / "phases"

        settings = OrchestratorSettings(
            repo_root=tmp_path,
            active_plans_dir=tmp_path / "active_plans",
            reviews_dir=tmp_path / "reviews",
        )
        (tmp_path / "reviews").mkdir(exist_ok=True)

        for pf in sorted(phases_dir.glob("phase_*.md")):
            parsed = parse_plan(pf, plan_type=PlanType.COMPLEX)
            assert len(parsed.tasks) > 0, f"No tasks in {pf.name}"
