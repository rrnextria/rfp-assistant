"""Integration tests for orchestrator_v3 (Phase 5).

Tests cross-module integration including dry-run validation,
mock plan/code review loops, and complex plan stage advancement.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from orchestrator_v3.cli import app
from orchestrator_v3.plan_tool import PlanVerificationResult

runner = CliRunner()


# ── Mock ORCH_META content (read from fixture files) ──────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
APPROVED_REVIEW = (FIXTURES_DIR / "mock_review_approved.md").read_text()
FIXES_REQUIRED_REVIEW = (FIXTURES_DIR / "mock_review_fixes_required.md").read_text()


# ── Helpers ───────────────────────────────────────────────────────────

def _mock_fixtures(base, round_reviews):
    """Create mock reviewer fixture directory with round-keyed review files."""
    d = base / "mock_fixtures"
    d.mkdir(parents=True, exist_ok=True)
    for round_num, content in round_reviews.items():
        (d / f"round{round_num}_review.md").write_text(content)
    return d


def _simple_plan(base, slug):
    """Create a single-file plan (no phases/ directory)."""
    plans = base / "active_plans"
    plans.mkdir(parents=True, exist_ok=True)
    f = plans / f"{slug}.md"
    f.write_text(
        f"# {slug} Plan\n\n"
        "## Tasks\n\n"
        "### [ ] 1 First Task\n\n"
        "  - [ ] 1.1 Subtask one\n"
        "  - [ ] 1.2 Subtask two\n\n"
        "### [ ] 2 Second Task\n\n"
        "  - [ ] 2.1 Subtask one\n"
    )
    return f


def _complex_plan(base, slug, num_phases=1):
    """Create a complex plan (master + phases/ directory)."""
    plan_dir = base / "active_plans" / slug
    phases_dir = plan_dir / "phases"
    phases_dir.mkdir(parents=True)
    for i in range(num_phases):
        pf = phases_dir / f"phase_{i}_test.md"
        pf.write_text(
            f"# Phase {i}\n\n"
            f"### [ ] 1 Task One\n\n"
            f"  - [ ] 1.1 Subtask one\n"
        )
    master = plan_dir / f"{slug}_master_plan.md"
    overview = "\n".join(f"- Phase {i}: Test" for i in range(num_phases))
    master.write_text(
        f"# {slug} Master Plan\n\n## Phases Overview\n\n{overview}\n"
    )
    return master


def _read_state(base, slug):
    """Load orchestrator state JSON (plan mode — campaign-level)."""
    return json.loads(
        (base / "reviews" / f"{slug}_orchestrator_state.json").read_text()
    )


def _read_task_state(base, slug, phase, task):
    """Load per-task state JSON (code mode — v3 per-task state)."""
    return json.loads(
        (base / "reviews" / f"{slug}_p{phase}_t{task}_state.json").read_text()
    )


# ── Task 1: Dry-Run — Complex Plan Detection ────────────────────────

class TestDryRunComplexPlan:
    """Dry-run detects complex plan structures correctly."""

    def test_1_phase_complex(self, tmp_path, monkeypatch):
        """1 phase + master = 2 stages."""
        slug = "dr_cx1"
        master = _complex_plan(tmp_path, slug, num_phases=1)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, ["plan", str(master), "--dry-run", "--init", "--skip-preflight"])

        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "ORCH_META" in result.output
        state = _read_state(tmp_path, slug)
        assert state["plan_type"] == "complex"
        assert state["total_stages"] == 2
        assert len(state["stage_files"]) == 2

    def test_5_phases_complex(self, tmp_path, monkeypatch):
        """5 phases + master = 6 stages."""
        slug = "dr_cx5"
        master = _complex_plan(tmp_path, slug, num_phases=5)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, ["plan", str(master), "--dry-run", "--init", "--skip-preflight"])

        assert result.exit_code == 0, result.output
        state = _read_state(tmp_path, slug)
        assert state["plan_type"] == "complex"
        assert state["total_stages"] == 6
        assert len(state["stage_files"]) == 6

    def test_stage_files_resolve(self, tmp_path, monkeypatch):
        """All stage_files in state point to existing files on disk."""
        slug = "dr_resolve"
        master = _complex_plan(tmp_path, slug, num_phases=3)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        runner.invoke(app, ["plan", str(master), "--dry-run", "--init", "--skip-preflight"])

        state = _read_state(tmp_path, slug)
        for sf in state["stage_files"]:
            assert Path(sf).exists(), f"Stage file missing: {sf}"

    def test_prompt_references_phase_and_master(self, tmp_path, monkeypatch):
        """Complex plan dry-run prompt references both phase and master files."""
        slug = "dr_prompt"
        master = _complex_plan(tmp_path, slug, num_phases=1)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, ["plan", str(master), "--dry-run", "--init", "--skip-preflight"])

        # Phase review prompt should reference the phase file and the master
        assert "phase_0_test" in result.output
        assert "master_plan" in result.output


# ── Task 1: Dry-Run — Simple Plan Detection ─────────────────────────

class TestDryRunSimplePlan:
    """Dry-run detects single-file plans correctly."""

    def test_simple_plan_detected(self, tmp_path, monkeypatch):
        """Single-file plan with no phases/ directory → simple type, 1 stage."""
        slug = "dr_simple"
        plan_file = _simple_plan(tmp_path, slug)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, ["plan", str(plan_file), "--dry-run", "--init", "--skip-preflight"])

        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "ORCH_META" in result.output
        state = _read_state(tmp_path, slug)
        assert state["plan_type"] == "simple"
        assert state["total_stages"] == 1

    def test_simple_prompt_references_plan(self, tmp_path, monkeypatch):
        """Simple plan prompt includes plan file path."""
        slug = "dr_simple_ref"
        plan_file = _simple_plan(tmp_path, slug)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, ["plan", str(plan_file), "--dry-run", "--init", "--skip-preflight"])

        assert "PLAN FILE TO REVIEW:" in result.output
        assert slug in result.output


# ── Task 1: Dry-Run — Code Mode ─────────────────────────────────────

class TestDryRunCodeMode:
    """Dry-run in code mode."""

    def test_code_complex(self, tmp_path, monkeypatch):
        """Code dry-run for complex plan slug."""
        slug = "dr_code_cx"
        _complex_plan(tmp_path, slug, num_phases=2)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, ["code", slug, "0", "1", "--dry-run", "--init", "--skip-preflight"])

        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "ORCH_META" in result.output
        state = _read_task_state(tmp_path, slug, 0, 1)
        assert state["mode"] == "code"
        assert state["phase"] == 0
        assert state["task"] == 1
        # B1 regression: complex plan code mode must include phase plan reference
        assert "Master Plan:" in result.output
        assert "Phase Plan:" in result.output

    def test_code_simple(self, tmp_path, monkeypatch):
        """Code dry-run for simple plan slug."""
        slug = "dr_code_sm"
        _simple_plan(tmp_path, slug)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, ["code", slug, "0", "1", "--dry-run", "--init", "--skip-preflight"])

        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        state = _read_task_state(tmp_path, slug, 0, 1)
        assert state["mode"] == "code"
        assert state["phase"] == 0
        assert state["task"] == 1

    def test_code_prompt_references_artifact(self, tmp_path, monkeypatch):
        """Code dry-run prompt includes code_complete artifact reference."""
        slug = "dr_code_art"
        _complex_plan(tmp_path, slug, num_phases=1)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, ["code", slug, "0", "1", "--dry-run", "--init", "--skip-preflight"])

        assert "CODE ARTIFACT TO REVIEW:" in result.output
        assert "code_complete" in result.output


# ── Task 2: Mock Plan Review Loop ────────────────────────────────────

class TestMockPlanReviewLoop:
    """Full plan review loop: R1 FIXES → pause → update → resume → R2 APPROVED."""

    def test_pause_resume_cycle(self, tmp_path, monkeypatch):
        slug = "planloop"  # avoid _plan suffix (stripped by _derive_slug)
        plan_file = _simple_plan(tmp_path, slug)
        (tmp_path / "reviews").mkdir()
        fixture_dir = _mock_fixtures(tmp_path, {
            1: FIXES_REQUIRED_REVIEW,
            2: APPROVED_REVIEW,
        })
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        # ── Round 1: FIXES_REQUIRED → pause ──
        r1 = runner.invoke(app, [
            "plan", str(plan_file),
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--init",
            "--skip-preflight",
        ])
        assert r1.exit_code == 0, r1.output

        state = _read_state(tmp_path, slug)
        assert state["status"] == "needs_response"
        assert state["current_round"] == 1

        review1 = tmp_path / "reviews" / f"{slug}_plan_review_round1.md"
        assert review1.exists()
        assert "FIXES_REQUIRED" in review1.read_text()

        # Verify waiting banner
        assert "resume" in r1.output.lower() or "PAUSED" in r1.output

        # ── Create planner update ──
        update = tmp_path / "reviews" / f"{slug}_plan_update_round1.md"
        update.write_text(
            "# Planner Update — Round 1\n\n"
            "## Findings Addressed\n\n"
            "| ID | Status |\n"
            "|----|--------|\n"
            "| M1 | FIXED |\n"
            "| N1 | FIXED |\n"
            "| N2 | FIXED |\n"
        )

        # ── Round 2: Resume → APPROVED ──
        r2 = runner.invoke(app, [
            "plan", str(plan_file),
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--resume",
            "--skip-preflight",
        ])
        assert r2.exit_code == 0, r2.output

        state = _read_state(tmp_path, slug)
        assert state["status"] == "approved"

        review2 = tmp_path / "reviews" / f"{slug}_plan_review_round2.md"
        assert review2.exists()
        assert "APPROVED" in review2.read_text()

        # Verify history
        assert len(state["history"]) == 2
        assert state["history"][0]["outcome"] == "fixes_required"
        assert state["history"][1]["outcome"] == "approved"


# ── Task 3: Mock Code Review Loop ────────────────────────────────────

class TestMockCodeReviewLoop:
    """Full code review loop: R1 FIXES → pause → response → resume → R2 APPROVED."""

    def test_pause_resume_cycle(self, tmp_path, monkeypatch):
        slug = "int_code"
        _complex_plan(tmp_path, slug, num_phases=1)
        reviews = tmp_path / "reviews"
        reviews.mkdir()
        fixture_dir = _mock_fixtures(tmp_path, {
            1: FIXES_REQUIRED_REVIEW,
            2: APPROVED_REVIEW,
        })

        # Create code_complete artifact (required for code mode)
        (reviews / f"{slug}_phase_0_task_1_code_complete_round1.md").write_text(
            "# Code Complete — Phase 0, Task 1\n\n## Files\n\nsrc/main.py\n"
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        # ── Round 1: FIXES_REQUIRED → pause ──
        r1 = runner.invoke(app, [
            "code", slug, "0", "1",
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--init",
            "--skip-preflight",
        ])
        assert r1.exit_code == 0, r1.output

        state = _read_task_state(tmp_path, slug, 0, 1)
        assert state["status"] == "needs_response"
        assert state["mode"] == "code"

        review1 = reviews / f"{slug}_phase_0_task_1_code_review_round1.md"
        assert review1.exists()
        assert "FIXES_REQUIRED" in review1.read_text()

        # ── Create coder response and code_complete for round 2 ──
        (reviews / f"{slug}_phase_0_task_1_coder_response_round1.md").write_text(
            "# Coder Response — Round 1\n\n"
            "| ID | Status |\n|----|--------|\n| M1 | FIXED |\n"
        )
        (reviews / f"{slug}_phase_0_task_1_code_complete_round2.md").write_text(
            "# Code Complete — Phase 0, Task 1 (Round 2)\n\n## Files\n\nsrc/main.py\n"
        )

        # ── Round 2: Resume → APPROVED → COMPLETE ──
        r2 = runner.invoke(app, [
            "code", slug, "0", "1",
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--resume",
            "--skip-preflight",
        ])
        assert r2.exit_code == 0, r2.output

        state = _read_task_state(tmp_path, slug, 0, 1)
        # After code approval, per-task state → APPROVED
        assert state["status"] == "approved"

        review2 = reviews / f"{slug}_phase_0_task_1_code_review_round2.md"
        assert review2.exists()
        assert "APPROVED" in review2.read_text()

        assert len(state["history"]) == 2
        assert state["history"][0]["outcome"] == "fixes_required"
        assert state["history"][1]["outcome"] == "approved"


# ── Task 4: Mock Complex Plan Stages ─────────────────────────────────

class TestMockComplexPlanStages:
    """Complex plan stage advancement with mock reviewer."""

    def test_two_stage_full_approval(self, tmp_path, monkeypatch):
        """1 phase + master: both APPROVED in round 1 → final APPROVED."""
        slug = "int_2stg"
        master = _complex_plan(tmp_path, slug, num_phases=1)
        (tmp_path / "reviews").mkdir()
        fixture_dir = _mock_fixtures(tmp_path, {1: APPROVED_REVIEW})
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, [
            "plan", str(master),
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--init",
            "--skip-preflight",
        ])
        assert result.exit_code == 0, result.output

        state = _read_state(tmp_path, slug)
        assert state["status"] == "approved"
        assert len(state["history"]) == 2
        assert all(h["outcome"] == "approved" for h in state["history"])

    def test_three_stage_full_approval(self, tmp_path, monkeypatch):
        """2 phases + master: all 3 stages APPROVED."""
        slug = "int_3stg"
        master = _complex_plan(tmp_path, slug, num_phases=2)
        (tmp_path / "reviews").mkdir()
        fixture_dir = _mock_fixtures(tmp_path, {1: APPROVED_REVIEW})
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, [
            "plan", str(master),
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--init",
            "--skip-preflight",
        ])
        assert result.exit_code == 0, result.output

        state = _read_state(tmp_path, slug)
        assert state["status"] == "approved"
        assert len(state["history"]) == 3

    def test_stage_artifacts_created(self, tmp_path, monkeypatch):
        """Review artifacts created for both stages with distinct names."""
        slug = "int_art"
        master = _complex_plan(tmp_path, slug, num_phases=1)
        (tmp_path / "reviews").mkdir()
        fixture_dir = _mock_fixtures(tmp_path, {1: APPROVED_REVIEW})
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        runner.invoke(app, [
            "plan", str(master),
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--init",
            "--skip-preflight",
        ])

        reviews = tmp_path / "reviews"
        # Stage 1: phase file review
        stage1 = list(reviews.glob(f"{slug}_phase_0_test_review_round*.md"))
        assert len(stage1) == 1, f"Stage 1 reviews: {stage1}"
        # Stage 2: master plan review
        stage2 = list(reviews.glob(f"{slug}_{slug}_master_plan_review_round*.md"))
        assert len(stage2) == 1, f"Stage 2 reviews: {stage2}"

    def test_stage_history_has_labels(self, tmp_path, monkeypatch):
        """History entries include stage_label for each stage."""
        slug = "int_labels"
        master = _complex_plan(tmp_path, slug, num_phases=1)
        (tmp_path / "reviews").mkdir()
        fixture_dir = _mock_fixtures(tmp_path, {1: APPROVED_REVIEW})
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        runner.invoke(app, [
            "plan", str(master),
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--init",
            "--skip-preflight",
        ])

        state = _read_state(tmp_path, slug)
        labels = [h.get("stage_label") for h in state["history"]]
        assert "phase_0_test" in labels
        assert f"{slug}_master_plan" in labels

    def test_two_stage_resume(self, tmp_path, monkeypatch):
        """7.9: Approve stage 0 via resume, verify stage 1 starts at round 1."""
        slug = "int_resume"
        master = _complex_plan(tmp_path, slug, num_phases=1)
        reviews = tmp_path / "reviews"
        reviews.mkdir()
        fixture_dir = _mock_fixtures(tmp_path, {
            1: FIXES_REQUIRED_REVIEW,
            2: APPROVED_REVIEW,
        })
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        # ── Init: stage 0 R1 FIXES_REQUIRED → pauses ──
        r1 = runner.invoke(app, [
            "plan", str(master),
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--init",
            "--skip-preflight",
        ])
        assert r1.exit_code == 0, r1.output
        state = _read_state(tmp_path, slug)
        assert state["current_stage"] == 0
        assert state["status"] == "needs_response"

        # Create planner update for stage 0
        (reviews / f"{slug}_phase_0_test_update_round1.md").write_text(
            "# Planner Update — phase_0_test Round 1\n\n"
            "| ID | Status |\n|----|--------|\n| M1 | FIXED |\n"
        )

        # ── Resume: stage 0 R2 APPROVED → advance to stage 1 R1 FIXES → pauses ──
        r2 = runner.invoke(app, [
            "plan", str(master),
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--resume",
            "--skip-preflight",
        ])
        assert r2.exit_code == 0, r2.output
        state = _read_state(tmp_path, slug)
        assert state["current_stage"] == 1
        assert state["status"] == "needs_response"

        # Verify stage 1 started at round 1 (not re-reviewing stage 0)
        stage1_review = reviews / f"{slug}_{slug}_master_plan_review_round1.md"
        assert stage1_review.exists(), (
            "Stage 1 (master) should have a round 1 review artifact"
        )

        # Verify stage 0 has both rounds
        assert (reviews / f"{slug}_phase_0_test_review_round1.md").exists()
        assert (reviews / f"{slug}_phase_0_test_review_round2.md").exists()

        # Create planner update for stage 1
        (reviews / f"{slug}_{slug}_master_plan_update_round1.md").write_text(
            "# Planner Update — master_plan Round 1\n\n"
            "| ID | Status |\n|----|--------|\n| M1 | FIXED |\n"
        )

        # ── Resume: stage 1 R2 APPROVED → all done ──
        r3 = runner.invoke(app, [
            "plan", str(master),
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--resume",
            "--skip-preflight",
        ])
        assert r3.exit_code == 0, r3.output
        state = _read_state(tmp_path, slug)
        assert state["status"] == "approved"
        assert len(state["history"]) == 4  # S0R1 + S0R2 + S1R1 + S1R2


# ── Real Repo Plan Helpers ────────────────────────────────────────────

# Repo root (parent of how_to/orchestrator_v3/tests/)
REPO_ROOT = Path(__file__).resolve().parents[3]


def _link_real_plans(tmp_path):
    """Symlink real active_plans/ into tmp_path for historical plan tests."""
    src = REPO_ROOT / "active_plans"
    if not src.is_dir():
        pytest.skip("active_plans/ not found at repo root")
    (tmp_path / "active_plans").symlink_to(src)
    (tmp_path / "reviews").mkdir(exist_ok=True)


# ── Task 1 (M1): Dry-Run Against Real Repo Plans ─────────────────────

@pytest.mark.skip(reason="Requires training-repo-specific plan files not present in standalone repo")
class TestDryRunHistoricalPlans:
    """Dry-run against the real repo plan structures (subtasks 1.1-1.6)."""

    def test_deferred_sync_plan_mode(self, tmp_path, monkeypatch):
        """1.1: deferred_sync_optimization plan mode — complex, 2 stages."""
        _link_real_plans(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")
        master = "active_plans/deferred_sync_optimization/deferred_sync_optimization_master_plan.md"

        result = runner.invoke(app, ["plan", master, "--dry-run", "--init"])

        assert result.exit_code == 0, result.output
        state = _read_state(tmp_path, "deferred_sync_optimization")
        assert state["plan_type"] == "complex"
        assert state["total_stages"] == 2
        assert "phase_0_deferred_sync" in result.output
        assert "master_plan" in result.output
        for sf in state["stage_files"]:
            assert Path(sf).exists(), f"Stage file missing: {sf}"

    def test_deferred_sync_code_mode(self, tmp_path, monkeypatch):
        """1.2: deferred_sync_optimization code mode — master + phase plan refs."""
        _link_real_plans(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(
            app, ["code", "deferred_sync_optimization", "0", "1", "--dry-run", "--init"]
        )

        assert result.exit_code == 0, result.output
        assert "Master Plan:" in result.output
        assert "Phase Plan:" in result.output
        assert "phase_0_deferred_sync" in result.output
        assert "code_complete" in result.output

    def test_cli_overrides_plan_mode(self, tmp_path, monkeypatch):
        """1.3: cli_overrides_runtime_yaml plan mode — simple, 1 stage."""
        _link_real_plans(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")
        plan_file = "active_plans/cli_overrides_runtime_yaml.md"

        result = runner.invoke(app, ["plan", plan_file, "--dry-run", "--init"])

        assert result.exit_code == 0, result.output
        state = _read_state(tmp_path, "cli_overrides_runtime_yaml")
        assert state["plan_type"] == "simple"
        assert state["total_stages"] == 1
        assert "cli_overrides_runtime_yaml" in result.output

    def test_cli_overrides_code_mode(self, tmp_path, monkeypatch):
        """1.4: cli_overrides_runtime_yaml code mode — simple, no phase ref."""
        _link_real_plans(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(
            app, ["code", "cli_overrides_runtime_yaml", "0", "1", "--dry-run", "--init"]
        )

        assert result.exit_code == 0, result.output
        state = _read_task_state(tmp_path, "cli_overrides_runtime_yaml", 0, 1)
        assert state["mode"] == "code"
        assert "Plan:" in result.output
        # Simple plan must NOT have Phase Plan line
        assert "Phase Plan:" not in result.output

    def test_fp8_training_code_mode(self, tmp_path, monkeypatch):
        """1.5: fp8_training code mode — master + phase_0 refs."""
        _link_real_plans(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(
            app, ["code", "fp8_training", "0", "1", "--dry-run", "--init"]
        )

        assert result.exit_code == 0, result.output
        assert "Master Plan:" in result.output
        assert "Phase Plan:" in result.output
        assert "phase_0_environment_and_baseline" in result.output

    def test_fp8_training_plan_mode(self, tmp_path, monkeypatch):
        """1.6: fp8_training plan mode — complex, 6 stages."""
        _link_real_plans(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")
        master = "active_plans/fp8_training/fp8_training_master_plan.md"

        result = runner.invoke(app, ["plan", master, "--dry-run", "--init"])

        assert result.exit_code == 0, result.output
        state = _read_state(tmp_path, "fp8_training")
        assert state["plan_type"] == "complex"
        assert state["total_stages"] == 6
        assert len(state["stage_files"]) == 6
        for sf in state["stage_files"]:
            assert Path(sf).exists(), f"Stage file missing: {sf}"


# ── Task 3.5/3.6: Preflight Validation Integration ───────────────────

class TestPreflightBlocksMalformedArtifact:
    """3.5: Preflight blocks review when code artifact is malformed."""

    @patch("orchestrator_v3.cli._run_env_preflight")
    @patch("orchestrator_v3.cli.verify_plan_syntax")
    def test_malformed_code_artifact_blocked(self, mock_verify, mock_env, tmp_path, monkeypatch):
        """Code artifact missing File: headings, ~~~diff fences, Test: lines
        should be blocked by preflight (state → needs_response)."""
        # Mock plan verification to pass (we're testing code preflight, not plan verification)
        mock_verify.return_value = PlanVerificationResult(
            passed=True, issues=[], summary="PASSED (0 errors, 0 warnings)"
        )

        slug = "pf_block"
        _complex_plan(tmp_path, slug, num_phases=1)
        reviews = tmp_path / "reviews"
        reviews.mkdir()
        fixture_dir = _mock_fixtures(tmp_path, {1: APPROVED_REVIEW})

        # Create a malformed code_complete artifact (no File:, no ~~~diff, no Test:)
        (reviews / f"{slug}_phase_0_task_1_code_complete_round1.md").write_text(
            "# Code Complete — Phase 0, Task 1\n\n"
            "Some changes were made.\n"
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        # Run WITHOUT --skip-preflight → should be blocked by code preflight
        r1 = runner.invoke(app, [
            "code", slug, "0", "1",
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--init",
        ])
        # Preflight failure pauses the loop (exit 0, state=needs_response)
        assert r1.exit_code == 0, r1.output
        assert "PREFLIGHT FAILED" in r1.output

        state = _read_task_state(tmp_path, slug, 0, 1)
        assert state["status"] == "needs_response"

        # M1 fix: preflight failure must NOT print the generic "Read the review" banner
        assert "Read the review" not in r1.output, (
            "Preflight failure should not print 'Read the review' banner"
        )

        # Reviewer should NOT have been called (no review file created)
        review1 = reviews / f"{slug}_phase_0_task_1_code_review_round1.md"
        assert not review1.exists(), "Reviewer should not run when preflight fails"


class TestSkipPreflightBypasses:
    """3.6: --skip-preflight bypasses preflight checks."""

    def test_skip_preflight_lets_malformed_through(self, tmp_path, monkeypatch):
        """Same malformed artifact but --skip-preflight allows review to proceed."""
        slug = "pf_skip"
        _complex_plan(tmp_path, slug, num_phases=1)
        reviews = tmp_path / "reviews"
        reviews.mkdir()
        fixture_dir = _mock_fixtures(tmp_path, {1: APPROVED_REVIEW})

        # Create same malformed code_complete artifact
        (reviews / f"{slug}_phase_0_task_1_code_complete_round1.md").write_text(
            "# Code Complete — Phase 0, Task 1\n\n"
            "Some changes were made.\n"
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        # Run WITH --skip-preflight → reviewer runs and approves
        r1 = runner.invoke(app, [
            "code", slug, "0", "1",
            "--mock-reviewer", str(fixture_dir),
            "--max-rounds", "5", "--init",
            "--skip-preflight",
        ])
        assert r1.exit_code == 0, r1.output
        assert "PREFLIGHT FAILED" not in r1.output

        state = _read_task_state(tmp_path, slug, 0, 1)
        assert state["status"] == "approved"

        # Reviewer was called — review file exists
        review1 = reviews / f"{slug}_phase_0_task_1_code_review_round1.md"
        assert review1.exists(), "Reviewer should run when preflight is skipped"


# ── Task 4.4: --skip-preflight CLI flag with --dry-run ────────────────

class TestSkipPreflightDryRun:
    """4.4: --skip-preflight flag is recognized in both code and plan modes."""

    def test_code_skip_preflight_dry_run(self, tmp_path, monkeypatch):
        """code --skip-preflight --dry-run succeeds and shows prompt."""
        slug = "pf_drycode"
        _complex_plan(tmp_path, slug, num_phases=1)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, [
            "code", slug, "0", "1",
            "--skip-preflight", "--dry-run", "--init",
        ])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output

    def test_plan_skip_preflight_dry_run(self, tmp_path, monkeypatch):
        """plan --skip-preflight --dry-run succeeds and shows prompt."""
        slug = "pf_dryplan"
        plan_file = _simple_plan(tmp_path, slug)
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, [
            "plan", str(plan_file),
            "--skip-preflight", "--dry-run", "--init",
        ])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output


# ── Task 5.5/5.6: Postmortem CLI ─────────────────────────────────────

class TestPostmortemCLI:
    """5.5/5.6: Postmortem CLI command tests."""

    def test_postmortem_help(self):
        """5.5: postmortem --help shows all flags."""
        result = runner.invoke(app, ["postmortem", "--help"])
        assert result.exit_code == 0, result.output
        assert "--skip-reflection" in result.output
        assert "--dry-run" in result.output
        assert "--model" in result.output

    def test_postmortem_no_artifacts(self, tmp_path, monkeypatch):
        """5.6: Nonexistent slug exits 0 with message."""
        (tmp_path / "reviews").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, [
            "postmortem", "nonexistent_slug", "--skip-reflection",
            "--skip-preflight",
        ])
        assert result.exit_code == 0, result.output
        assert "No review artifacts found" in result.output

    def test_postmortem_dry_run(self, tmp_path, monkeypatch):
        """Dry run lists artifacts without writing report."""
        reviews = tmp_path / "reviews"
        reviews.mkdir()
        (reviews / "test_phase_0_task_1_code_review_round1.md").write_text(
            "<!-- ORCH_META\nVERDICT: APPROVED\nBLOCKER: 0\n"
            "MAJOR: 0\nMINOR: 0\nDECISIONS: 0\nVERIFIED: 5\n-->\n# Review\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, ["postmortem", "test", "--dry-run", "--skip-preflight"])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "1 artifacts found" in result.output
        # No report file should be created
        assert not (reviews / "test_postmortem.md").exists()

    def test_postmortem_skip_reflection(self, tmp_path, monkeypatch):
        """Skip-reflection produces metrics-only report."""
        reviews = tmp_path / "reviews"
        reviews.mkdir()
        (reviews / "test_phase_0_task_1_code_review_round1.md").write_text(
            "<!-- ORCH_META\nVERDICT: APPROVED\nBLOCKER: 0\n"
            "MAJOR: 0\nMINOR: 0\nDECISIONS: 0\nVERIFIED: 5\n-->\n# Review\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, [
            "postmortem", "test", "--skip-reflection", "--skip-preflight",
        ])
        assert result.exit_code == 0, result.output
        assert "Postmortem written to" in result.output

        report = (reviews / "test_postmortem.md").read_text()
        assert "Campaign Postmortem: test" in report
        assert "Evolutionary Reflection" not in report


# ── Task 5 Regression: idle_timeout defaults ──────────────────────────

class TestIdleTimeoutDefaults:
    """Regression: idle_timeout must default to 600s (not 120s).

    Issue 1 from Phase 3 live validation: gpt-5.2 xhigh reasoning goes
    silent for 2-5 minutes; the original 120s default killed active reviews.
    """

    def test_codex_reviewer_default(self):
        """CodexReviewer.__init__ defaults idle_timeout to 600."""
        import inspect
        from orchestrator_v3.reviewer import CodexReviewer
        sig = inspect.signature(CodexReviewer.__init__)
        assert sig.parameters["idle_timeout"].default == 600

    def test_plan_cli_help_shows_600(self):
        """plan --help shows idle-timeout default of 600."""
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0, result.output
        # Typer shows "[default: 600]" for the idle-timeout option
        assert "idle-timeout" in result.output
        assert "600" in result.output

    def test_code_cli_help_shows_600(self):
        """code --help shows idle-timeout default of 600."""
        result = runner.invoke(app, ["code", "--help"])
        assert result.exit_code == 0, result.output
        assert "idle-timeout" in result.output
        assert "600" in result.output

    def test_postmortem_cli_help_shows_600(self):
        """postmortem --help shows idle-timeout default of 600."""
        result = runner.invoke(app, ["postmortem", "--help"])
        assert result.exit_code == 0, result.output
        assert "idle-timeout" in result.output
        assert "600" in result.output
