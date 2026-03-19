"""Tests for plan_status() and plan_show() — Phase 4 status & query operations."""

import json

import pytest
from typer.testing import CliRunner

from orchestrator_v3.cli import app
from orchestrator_v3.config import Mode, OrchestratorSettings, PlanType, Status
from orchestrator_v3.plan_tool import (
    PhaseProgress,
    ProgressSummary,
    plan_show,
    plan_status,
)
from orchestrator_v3.state import (
    CampaignManager,
    TaskState,
    TaskStateManager,
    campaign_index_path,
    task_state_path,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_simple_plan(settings: OrchestratorSettings, slug: str, num_tasks: int = 5) -> None:
    """Create a simple plan file with the given number of tasks."""
    plan_file = settings.active_plans_dir / f"{slug}.md"
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {slug.replace('_', ' ').title()} Plan",
        "",
        "**Status:** Pending",
        "",
        "---",
        "",
        "## Objective",
        "",
        "Test objective.",
        "",
        "## Current vs Desired",
        "",
        "Current: nothing. Desired: something.",
        "",
        "## Scope",
        "",
        "In scope: everything.",
        "",
        "## Policies & Contracts",
        "",
        "None.",
        "",
        "## Tasks",
        "",
    ]
    for i in range(1, num_tasks + 1):
        lines.append(f"### [ ] {i} Task {i} Title")
        lines.append(f"")
        lines.append(f"Description for task {i}.")
        lines.append(f"")
        lines.append(f"#### [ ] {i}.1 Subtask {i}.1")
        lines.append(f"")
        lines.append(f"  - [ ] {i}.1.1 Step {i}.1.1")
        lines.append(f"")

    lines.extend([
        "## Acceptance Criteria",
        "",
        "- [ ] All tasks done.",
        "",
        "## Risks & Mitigations",
        "",
        "None.",
        "",
        "## Validation",
        "",
        "Run tests.",
        "",
        "## Artifacts Created",
        "",
        "None.",
        "",
        "## Interfaces & Dependencies",
        "",
        "None.",
        "",
        "## References",
        "",
        "None.",
        "",
        "## Reviewer Checklist",
        "",
        "- [ ] All good.",
        "",
    ])
    plan_file.write_text("\n".join(lines))


def _create_complex_plan(
    settings: OrchestratorSettings,
    slug: str,
    phases: list[tuple[str, int]],
) -> None:
    """Create a complex plan with master + phase files.

    Args:
        phases: list of (phase_name, num_tasks) tuples.
    """
    plan_dir = settings.active_plans_dir / slug
    phases_dir = plan_dir / "phases"
    phases_dir.mkdir(parents=True, exist_ok=True)

    # Master plan
    master = plan_dir / f"{slug}_master_plan.md"
    master_lines = [
        f"# {slug.replace('_', ' ').title()} Master Plan",
        "",
        "## Executive Summary",
        "",
        "Test master plan.",
        "",
        "## Phases Overview",
        "",
    ]
    for i, (name, _) in enumerate(phases):
        master_lines.append(f"### Phase {i}: {name}")
        master_lines.append("")
    master.write_text("\n".join(master_lines))

    # Phase files
    for i, (name, num_tasks) in enumerate(phases):
        phase_file = phases_dir / f"phase_{i}_{name.lower().replace(' ', '_')}.md"
        lines = [
            f"# Phase {i}: {name}",
            "",
            "**Status:** Pending",
            "",
            "---",
            "",
            "## Detailed Objective",
            "",
            f"Objective for phase {i}.",
            "",
            "## Tasks",
            "",
        ]
        for t in range(1, num_tasks + 1):
            lines.append(f"### [ ] {t} Task {t} in phase {i}")
            lines.append(f"")
            lines.append(f"Description for task {t}.")
            lines.append(f"")
            lines.append(f"  - [ ] {t}.1 Subtask {t}.1")
            lines.append(f"")
        phase_file.write_text("\n".join(lines))


def _create_campaign_index(
    settings: OrchestratorSettings,
    slug: str,
    current_phase: int = 0,
    current_task: int = 1,
    total_phases: int = 1,
    tasks_per_phase: dict[str, int] | None = None,
    status: Status = Status.NEEDS_REVIEW,
) -> None:
    """Create a campaign index file."""
    cm = CampaignManager(
        state_path=campaign_index_path(slug, settings),
        settings=settings,
    )
    cm.init(
        slug=slug,
        mode=Mode.CODE,
        plan_file=f"active_plans/{slug}/{slug}_master_plan.md",
        total_phases=total_phases,
        tasks_per_phase=tasks_per_phase or {"0": 1},
        current_phase=current_phase,
        current_task=current_task,
    )
    # If status should be set to complete, update it
    if status == Status.COMPLETE:
        ci = cm.load()
        ci_updated = ci.model_copy(update={"status": Status.COMPLETE})
        cm.save(ci_updated)


def _create_task_state(
    settings: OrchestratorSettings,
    slug: str,
    phase: int,
    task: int,
    status: Status = Status.APPROVED,
    history: list[dict] | None = None,
) -> None:
    """Create a per-task state file."""
    ts_path = task_state_path(slug, phase, task, settings)
    tsm = TaskStateManager(state_path=ts_path)
    tsm.init(
        slug=slug,
        phase=phase,
        task=task,
        plan_file=f"active_plans/{slug}/{slug}_master_plan.md",
        mode=Mode.CODE,
    )
    # Update status and history
    updates = {"status": status}
    if history is not None:
        updates["history"] = history
    tsm.update(**updates)


# ---------------------------------------------------------------------------
# Test 6.1: plan_status with completed campaign
# ---------------------------------------------------------------------------

class TestPlanStatusCompleted:
    def test_completed_campaign_100_percent(self, tmp_settings):
        slug = "completed_camp"
        _create_simple_plan(tmp_settings, slug, num_tasks=3)
        _create_campaign_index(
            tmp_settings, slug, total_phases=1,
            tasks_per_phase={"0": 1},  # Buggy value
            status=Status.COMPLETE,
        )
        # Create approved task states
        for t in range(1, 4):
            _create_task_state(tmp_settings, slug, phase=0, task=t, status=Status.APPROVED)

        result = plan_status(slug, tmp_settings)
        assert result.percent == 100.0
        assert result.total_completed == result.total_tasks
        assert result.total_tasks == 3  # From parser, not from campaign index
        for pb in result.phase_breakdown:
            assert pb.completed_tasks == pb.total_tasks


# ---------------------------------------------------------------------------
# Test 6.2: plan_status with partially completed campaign
# ---------------------------------------------------------------------------

class TestPlanStatusPartial:
    def test_partial_campaign_correct_percentage(self, tmp_settings):
        slug = "partial_camp"
        _create_complex_plan(
            tmp_settings, slug,
            phases=[("Setup", 2), ("Build", 2), ("Test", 2)],
        )
        _create_campaign_index(
            tmp_settings, slug, current_phase=1, current_task=2,
            total_phases=3,
            tasks_per_phase={"0": 2, "1": 2, "2": 2},
        )
        # Complete 3 of 6 tasks: phase 0 both tasks, phase 1 task 1
        _create_task_state(tmp_settings, slug, phase=0, task=1, status=Status.APPROVED)
        _create_task_state(tmp_settings, slug, phase=0, task=2, status=Status.APPROVED)
        _create_task_state(tmp_settings, slug, phase=1, task=1, status=Status.APPROVED)

        result = plan_status(slug, tmp_settings)
        assert result.total_tasks == 6
        assert result.total_completed == 3
        assert result.percent == 50.0
        assert result.phase_breakdown[0].completed_tasks == 2
        assert result.phase_breakdown[1].completed_tasks == 1
        assert result.phase_breakdown[2].completed_tasks == 0


# ---------------------------------------------------------------------------
# Test 6.3: Simple plan derives task count from parser, not CampaignIndex
# ---------------------------------------------------------------------------

class TestSimplePlanTaskCount:
    def test_task_count_from_parser_not_campaign(self, tmp_settings):
        slug = "simple_bug"
        _create_simple_plan(tmp_settings, slug, num_tasks=5)
        # Campaign index has the buggy tasks_per_phase={"0": 1}
        _create_campaign_index(
            tmp_settings, slug, total_phases=1,
            tasks_per_phase={"0": 1},  # BUG: should be 5
        )

        result = plan_status(slug, tmp_settings)
        # plan_status must derive from parser, so total_tasks should be 5
        assert result.total_tasks == 5


# ---------------------------------------------------------------------------
# Test 6.4: plan_show --current extracts correct task subtree
# ---------------------------------------------------------------------------

class TestPlanShowCurrent:
    def test_current_extracts_correct_task(self, tmp_settings):
        slug = "show_current"
        _create_simple_plan(tmp_settings, slug, num_tasks=3)
        # Set state to phase 0, task 2
        _create_campaign_index(
            tmp_settings, slug, current_phase=0, current_task=2,
            total_phases=1, tasks_per_phase={"0": 3},
        )

        result = plan_show(slug, tmp_settings, current=True)
        # Should contain task 2's heading
        assert "Task 2 Title" in result
        # Should NOT contain task 1 or task 3 headings
        assert "### [ ] 1 Task 1 Title" not in result
        assert "### [ ] 3 Task 3 Title" not in result

    def test_current_stale_pointer_warning(self, tmp_settings):
        slug = "show_stale"
        _create_simple_plan(tmp_settings, slug, num_tasks=3)
        _create_campaign_index(
            tmp_settings, slug, current_phase=0, current_task=99,
            total_phases=1, tasks_per_phase={"0": 3},
        )

        result = plan_show(slug, tmp_settings, current=True)
        assert "Warning" in result or "not found" in result


# ---------------------------------------------------------------------------
# Test 6.5: plan_show --recent shows approved tasks by timestamp
# ---------------------------------------------------------------------------

class TestPlanShowRecent:
    def test_recent_sorted_by_timestamp(self, tmp_settings):
        slug = "show_recent"
        _create_simple_plan(tmp_settings, slug, num_tasks=3)
        _create_campaign_index(
            tmp_settings, slug, current_phase=0, current_task=3,
            total_phases=1, tasks_per_phase={"0": 3},
        )
        # Create task states with approval history
        _create_task_state(
            tmp_settings, slug, phase=0, task=1, status=Status.APPROVED,
            history=[{"round": 2, "action": "review", "outcome": "approved",
                       "timestamp": "2026-03-10T10:00:00Z"}],
        )
        _create_task_state(
            tmp_settings, slug, phase=0, task=2, status=Status.APPROVED,
            history=[{"round": 1, "action": "review", "outcome": "approved",
                       "timestamp": "2026-03-12T10:00:00Z"}],
        )
        _create_task_state(
            tmp_settings, slug, phase=0, task=3, status=Status.NEEDS_REVIEW,
            history=[{"round": 3, "action": "review", "outcome": "approved",
                       "timestamp": "2026-03-11T10:00:00Z"}],
        )

        result = plan_show(slug, tmp_settings, recent=True)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        # Most recent first: task 2 (Mar 12), task 3 (Mar 11), task 1 (Mar 10)
        assert "Task 2" in lines[0]
        assert "Task 3" in lines[1]
        assert "Task 1" in lines[2]

    def test_recent_no_approved(self, tmp_settings):
        slug = "no_approved"
        _create_simple_plan(tmp_settings, slug, num_tasks=2)
        _create_campaign_index(
            tmp_settings, slug, current_phase=0, current_task=1,
            total_phases=1, tasks_per_phase={"0": 2},
        )

        result = plan_show(slug, tmp_settings, recent=True)
        assert "No approved tasks" in result


# ---------------------------------------------------------------------------
# Test 6.6: plan_show default mode with status icons
# ---------------------------------------------------------------------------

class TestPlanShowDefault:
    def test_default_shows_status_icons(self, tmp_settings):
        slug = "show_default"
        _create_simple_plan(tmp_settings, slug, num_tasks=3)
        _create_campaign_index(
            tmp_settings, slug, current_phase=0, current_task=2,
            total_phases=1, tasks_per_phase={"0": 3},
        )
        # Mark task 1 as approved
        _create_task_state(tmp_settings, slug, phase=0, task=1, status=Status.APPROVED)

        result = plan_show(slug, tmp_settings)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        # Task 1 should be completed
        assert "[completed]" in lines[0]
        assert "Task 1 Title" in lines[0]
        # Tasks 2 and 3 should be pending
        assert "[pending]" in lines[1]
        assert "[pending]" in lines[2]

    def test_default_complex_plan_groups_by_phase(self, tmp_settings):
        slug = "show_complex"
        _create_complex_plan(
            tmp_settings, slug,
            phases=[("Setup", 2), ("Build", 1)],
        )

        result = plan_show(slug, tmp_settings)
        assert "Phase 0:" in result
        assert "Phase 1:" in result
        assert "Setup" in result
        assert "Build" in result


# ---------------------------------------------------------------------------
# Test 6.7: CLI plan-status --json outputs valid JSON
# ---------------------------------------------------------------------------

class TestCLIPlanStatusJson:
    def test_json_output_valid(self, tmp_path, monkeypatch):
        slug = "cli_json"
        settings = OrchestratorSettings(repo_root=tmp_path)
        settings.reviews_dir.mkdir(parents=True, exist_ok=True)
        settings.active_plans_dir.mkdir(parents=True, exist_ok=True)
        _create_simple_plan(settings, slug, num_tasks=3)

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["plan-status", slug, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Verify all ProgressSummary fields present
        for key in ("slug", "current_phase", "current_task", "total_phases",
                     "total_tasks", "total_completed", "percent", "phase_breakdown"):
            assert key in data
        assert data["slug"] == slug
        assert data["total_tasks"] == 3


# ---------------------------------------------------------------------------
# Test 6.8: CLI plan-status without --json outputs human text
# ---------------------------------------------------------------------------

class TestCLIPlanStatusText:
    def test_text_output_contains_slug_and_percent(self, tmp_path, monkeypatch):
        slug = "cli_text"
        settings = OrchestratorSettings(repo_root=tmp_path)
        settings.reviews_dir.mkdir(parents=True, exist_ok=True)
        settings.active_plans_dir.mkdir(parents=True, exist_ok=True)
        _create_simple_plan(settings, slug, num_tasks=2)

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["plan-status", slug])
        assert result.exit_code == 0
        assert slug in result.output
        assert "%" in result.output


# ---------------------------------------------------------------------------
# Test 6.9: CLI plan-show --current --recent prints error
# ---------------------------------------------------------------------------

class TestCLIPlanShowMutualExclusive:
    def test_current_and_recent_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["plan-show", "any_slug", "--current", "--recent"])
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output.lower() or "mutually exclusive" in (result.output + (result.stderr or "")).lower()


# ---------------------------------------------------------------------------
# Test 6.10: Edge case — empty campaign returns 0%
# ---------------------------------------------------------------------------

class TestEmptyCampaign:
    def test_empty_campaign_0_percent(self, tmp_settings):
        slug = "empty_camp"
        _create_simple_plan(tmp_settings, slug, num_tasks=3)
        _create_campaign_index(
            tmp_settings, slug, total_phases=1,
            tasks_per_phase={"0": 1},
        )

        result = plan_status(slug, tmp_settings)
        assert result.percent == 0.0
        assert result.total_completed == 0
        assert result.total_tasks == 3  # From parser


# ---------------------------------------------------------------------------
# Test 6.11: Edge case — no per-task state files
# ---------------------------------------------------------------------------

class TestNoTaskStateFiles:
    def test_no_state_files_0_completed(self, tmp_settings):
        slug = "no_state"
        _create_simple_plan(tmp_settings, slug, num_tasks=4)
        # Only campaign index, no per-task state files
        _create_campaign_index(
            tmp_settings, slug, total_phases=1,
            tasks_per_phase={"0": 1},
        )

        result = plan_status(slug, tmp_settings)
        assert result.total_tasks == 4  # From parser
        assert result.total_completed == 0
        assert result.percent == 0.0


# ---------------------------------------------------------------------------
# Test 6.12: Edge case — completed campaign override (no per-task states)
# ---------------------------------------------------------------------------

class TestCompletedCampaignOverride:
    def test_complete_status_overrides_missing_task_states(self, tmp_settings):
        slug = "complete_override"
        _create_simple_plan(tmp_settings, slug, num_tasks=5)
        _create_campaign_index(
            tmp_settings, slug, total_phases=1,
            tasks_per_phase={"0": 1},
            status=Status.COMPLETE,
        )
        # No per-task state files created — campaign-level override should
        # set all tasks to completed

        result = plan_status(slug, tmp_settings)
        assert result.total_tasks == 5  # From parser
        assert result.total_completed == 5
        assert result.percent == 100.0


# ---------------------------------------------------------------------------
# Additional: ProgressSummary model tests
# ---------------------------------------------------------------------------

class TestProgressSummaryModel:
    def test_to_json_all_fields(self):
        summary = ProgressSummary(
            slug="test",
            current_phase=1,
            current_task=2,
            total_phases=3,
            total_tasks=10,
            total_completed=4,
            percent=40.0,
            phase_breakdown=[
                PhaseProgress(phase=0, name="Setup", total_tasks=3, completed_tasks=3),
                PhaseProgress(phase=1, name="Build", total_tasks=4, completed_tasks=1),
                PhaseProgress(phase=2, name="Test", total_tasks=3, completed_tasks=0),
            ],
        )
        data = summary.to_json()
        assert data["slug"] == "test"
        assert data["total_tasks"] == 10
        assert data["percent"] == 40.0
        assert len(data["phase_breakdown"]) == 3

    def test_to_text_compact(self):
        summary = ProgressSummary(
            slug="plan_tool",
            current_phase=0,
            current_task=2,
            total_phases=4,
            total_tasks=7,
            total_completed=2,
            percent=28.0,
            phase_breakdown=[],
        )
        text = summary.to_text()
        assert "plan_tool" in text
        assert "Phase 1/4" in text
        assert "28%" in text

    def test_to_json_roundtrip(self):
        summary = ProgressSummary(
            slug="test",
            current_phase=0,
            current_task=1,
            total_phases=1,
            total_tasks=3,
            total_completed=0,
            percent=0.0,
            phase_breakdown=[
                PhaseProgress(phase=0, name="Main", total_tasks=3, completed_tasks=0),
            ],
        )
        json_str = json.dumps(summary.to_json())
        parsed = json.loads(json_str)
        assert parsed["total_tasks"] == 3


# ---------------------------------------------------------------------------
# Additional: plan_status with no state files (fallback to plan parsing)
# ---------------------------------------------------------------------------

class TestPlanStatusNoState:
    def test_no_state_falls_back_to_plan_parsing(self, tmp_settings):
        slug = "no_state_at_all"
        _create_simple_plan(tmp_settings, slug, num_tasks=3)
        # No campaign index, no orchestrator state — pure fallback

        result = plan_status(slug, tmp_settings)
        assert result.current_phase == 0
        assert result.current_task == 1
        assert result.total_tasks == 3
        assert result.total_completed == 0
        assert result.percent == 0.0
