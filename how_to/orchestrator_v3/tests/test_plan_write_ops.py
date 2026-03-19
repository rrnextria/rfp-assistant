"""Tests for plan write operations — Phase 5: plan_sync, plan_render_master, plan_reconcile, auto-trigger."""

import hashlib
import json
import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator_v3.config import Mode, OrchestratorSettings, PlanType, Status
from orchestrator_v3.plan_tool import (
    DriftReport,
    SyncResult,
    plan_reconcile,
    plan_render_master,
    plan_sync,
)
from orchestrator_v3.state import (
    CampaignManager,
    TaskState,
    TaskStateManager,
    campaign_index_path,
    task_state_path,
)

# ---------------------------------------------------------------------------
# Empirical data paths
# ---------------------------------------------------------------------------

EMPIRICAL_DIR = Path(__file__).resolve().parents[3] / "research" / "plan_automation" / "empirical_data"
TRITON_PLANS = EMPIRICAL_DIR / "triton_plans"
TRITON_REVIEWS = EMPIRICAL_DIR / "triton_reviews"
HAS_EMPIRICAL = TRITON_PLANS.is_dir() and TRITON_REVIEWS.is_dir()

CASTLEGUARD_DIR = Path("/home/ejkitchen/git/TitanAI/active_plans/castleguard_modernization")
HAS_CASTLEGUARD = CASTLEGUARD_DIR.is_dir()


# ---------------------------------------------------------------------------
# Helpers — fixture builders
# ---------------------------------------------------------------------------

def _create_phase_file(
    phases_dir: Path,
    phase_num: int,
    name: str,
    tasks: list[dict],
) -> Path:
    """Create a phase file with structured tasks.

    Each task dict has keys: number, title, subtasks (list of (number, title)),
    optionally leaf_steps (list of (number, title)).
    """
    lines = [
        f"# Phase {phase_num}: {name}",
        "",
        f"**Status:** Pending",
        f"**Last Updated:** 2026-03-13",
        "",
        "---",
        "",
        "## Detailed Objective",
        "",
        f"Objective for phase {phase_num}.",
        "",
        "## Deliverables Snapshot",
        "",
        "1. Deliverable one.",
        "",
        "## Acceptance Gates",
        "",
        "- [ ] Gate 1: First acceptance gate",
        "- [ ] Gate 2: Second acceptance gate",
        "",
        "## Scope",
        "",
        "- In Scope:",
        "  1. Item one",
        "  - [ ] Scope checkbox that should NOT be toggled",
        "- Out of Scope:",
        "  1. Nothing",
        "",
        "## Interfaces & Dependencies",
        "",
        "None.",
        "",
        "## Risks & Mitigations",
        "",
        "None.",
        "",
        "## Decision Log",
        "",
        "None.",
        "",
        "## References",
        "",
        "### Source Files",
        "",
        "None.",
        "",
        "### Destination Files",
        "",
        "None.",
        "",
        "### Related Documentation",
        "",
        "None.",
        "",
        "## Tasks",
        "",
    ]

    for t in tasks:
        num = t["number"]
        title = t["title"]
        checked = t.get("checked", False)
        mark = "\u2705" if checked else " "
        lines.append(f"### [{mark}] {num} {title}")
        lines.append(f"Description for task {num}.")
        lines.append("")
        for sub_num, sub_title in t.get("subtasks", []):
            sub_mark = "\u2705" if checked else " "
            lines.append(f"  - [{sub_mark}] {sub_num} {sub_title}")
        for leaf_num, leaf_title in t.get("leaf_steps", []):
            leaf_mark = "\u2705" if checked else " "
            lines.append(f"    - [{leaf_mark}] {leaf_num} {leaf_title}")
        lines.append("")

    lines.extend([
        "## Completion Step (Required)",
        "",
        "Run tests.",
        "",
        "## Reviewer Checklist",
        "",
        "### Structure & Numbering",
        "",
        "- [ ] All top-level tasks use `### [ ] N` format.",
        "- [ ] All sub-tasks use `- [ ] N.1` format.",
        "",
    ])

    phase_file = phases_dir / f"phase_{phase_num}_{name.lower().replace(' ', '_')}.md"
    phase_file.write_text("\n".join(lines))
    return phase_file


def _create_master_plan(plan_dir: Path, slug: str, phases: list[tuple[int, str]]) -> Path:
    """Create a master plan with Phases Overview section."""
    lines = [
        f"# {slug.replace('_', ' ').title()} Master Plan",
        "",
        "## Executive Summary",
        "",
        "Test master plan.",
        "",
        "## Detailed Objective",
        "",
        "Test objective.",
        "",
        "## Quick Navigation",
        "",
        "None.",
        "",
        "## Architecture Overview",
        "",
        "None.",
        "",
        "## Current State",
        "",
        "None.",
        "",
        "## Desired State",
        "",
        "None.",
        "",
        "## Global Risks & Mitigations",
        "",
        "None.",
        "",
        "## Global Acceptance Gates",
        "",
        "- [ ] Gate 1: All tests pass.",
        "",
        "## Dependency Gates",
        "",
        "None.",
        "",
        "## Phases Overview",
        "",
    ]
    for pnum, pname in phases:
        lines.append(f"### Phase {pnum}: {pname}")
        lines.append("")

    lines.extend([
        "## Decision Log",
        "",
        "None.",
        "",
        "## References",
        "",
        "### Source Files",
        "",
        "None.",
        "",
        "### Destination Files",
        "",
        "None.",
        "",
        "### Related Documentation",
        "",
        "None.",
        "",
        "## Reviewer Checklist",
        "",
        "- [ ] All good.",
        "",
    ])

    master_file = plan_dir / f"{slug}_master_plan.md"
    master_file.write_text("\n".join(lines))
    return master_file


def _create_test_plan(
    settings: OrchestratorSettings,
    slug: str,
    phase_specs: list[tuple[str, list[dict]]],
) -> Path:
    """Create a complete complex plan fixture with master + phases.

    phase_specs: list of (name, tasks_list) tuples. Each task dict has
    number, title, subtasks, optionally leaf_steps.
    """
    plan_dir = settings.active_plans_dir / slug
    phases_dir = plan_dir / "phases"
    phases_dir.mkdir(parents=True, exist_ok=True)

    for i, (name, tasks) in enumerate(phase_specs):
        _create_phase_file(phases_dir, i, name, tasks)

    phases = [(i, name) for i, (name, _tasks) in enumerate(phase_specs)]
    master_file = _create_master_plan(plan_dir, slug, phases)
    return master_file


def _create_task_state(
    settings: OrchestratorSettings,
    slug: str,
    phase: int,
    task: int,
    status: Status = Status.APPROVED,
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
    tsm.update(status=status)


def _create_review_file(
    settings: OrchestratorSettings,
    slug: str,
    phase: int,
    task: int,
    round_num: int,
    verdict: str = "APPROVED",
) -> Path:
    """Create a mock review file with ORCH_META block."""
    name = f"{slug}_phase_{phase}_task_{task}_code_review_round{round_num}.md"
    review_file = settings.reviews_dir / name
    content = f"""<!-- ORCH_META
VERDICT: {verdict}
BLOCKER: 0
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 5
-->

# Review for phase {phase} task {task} round {round_num}

All good.
"""
    review_file.write_text(content)
    return review_file


# ---------------------------------------------------------------------------
# Test 7: plan_sync unit tests
# ---------------------------------------------------------------------------


class TestPlanSync:
    """Unit tests for plan_sync()."""

    def test_toggles_correct_heading(self, tmp_settings):
        """7.1: plan_sync toggles ### [ ] 2 to ### [checkmark] 2."""
        slug = "sync_heading"
        _create_test_plan(tmp_settings, slug, [
            ("Setup", [
                {"number": 1, "title": "First Task", "subtasks": [("1.1", "Sub 1.1")]},
                {"number": 2, "title": "Second Task", "subtasks": [("2.1", "Sub 2.1"), ("2.2", "Sub 2.2")]},
                {"number": 3, "title": "Third Task", "subtasks": [("3.1", "Sub 3.1")]},
            ]),
        ])

        result = plan_sync(slug, 0, 2, tmp_settings)
        assert result.files_updated == 1
        assert result.checkmarks_toggled >= 1

        # Verify the file was updated
        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_setup.md"
        content = phase_file.read_text()
        assert "### [\u2705] 2 Second Task" in content
        # Task 1 and 3 should still be unchecked
        assert "### [ ] 1 First Task" in content
        assert "### [ ] 3 Third Task" in content

    def test_toggles_subtask_checkboxes(self, tmp_settings):
        """7.2: plan_sync toggles all subtask checkboxes."""
        slug = "sync_subs"
        _create_test_plan(tmp_settings, slug, [
            ("Build", [
                {"number": 1, "title": "Build Task", "subtasks": [
                    ("1.1", "Sub 1.1"), ("1.2", "Sub 1.2"), ("1.3", "Sub 1.3"),
                ]},
            ]),
        ])

        result = plan_sync(slug, 0, 1, tmp_settings)
        assert result.checkmarks_toggled == 4  # heading + 3 subtasks

        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_build.md"
        content = phase_file.read_text()
        assert "### [\u2705] 1 Build Task" in content
        assert "[\u2705] 1.1 Sub 1.1" in content
        assert "[\u2705] 1.2 Sub 1.2" in content
        assert "[\u2705] 1.3 Sub 1.3" in content

    def test_toggles_leaf_steps(self, tmp_settings):
        """7.3: plan_sync toggles N.M.K leaf step checkboxes (4-space indent)."""
        slug = "sync_leaf"
        _create_test_plan(tmp_settings, slug, [
            ("Deploy", [
                {"number": 1, "title": "Deploy Task", "subtasks": [
                    ("1.1", "Sub 1.1"), ("1.2", "Sub 1.2"),
                ], "leaf_steps": [
                    ("1.1.1", "Leaf 1.1.1"), ("1.1.2", "Leaf 1.1.2"),
                    ("1.2.1", "Leaf 1.2.1"),
                ]},
            ]),
        ])

        result = plan_sync(slug, 0, 1, tmp_settings)
        # heading + 2 subtasks + 3 leaf steps = 6
        assert result.checkmarks_toggled == 6

        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_deploy.md"
        content = phase_file.read_text()
        assert "[\u2705] 1.1.1 Leaf 1.1.1" in content
        assert "[\u2705] 1.1.2 Leaf 1.1.2" in content
        assert "[\u2705] 1.2.1 Leaf 1.2.1" in content

    def test_does_not_modify_acceptance_gates(self, tmp_settings):
        """7.4: plan_sync does NOT modify checkboxes in Acceptance Gates."""
        slug = "sync_gates"
        _create_test_plan(tmp_settings, slug, [
            ("Test", [
                {"number": 1, "title": "Test Task", "subtasks": [("1.1", "Sub 1.1")]},
            ]),
        ])

        plan_sync(slug, 0, 1, tmp_settings)
        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_test.md"
        content = phase_file.read_text()
        # Gates should still be unchecked
        assert "- [ ] Gate 1:" in content
        assert "- [ ] Gate 2:" in content

    def test_does_not_modify_scope_section(self, tmp_settings):
        """7.5: plan_sync does NOT modify checkboxes in Scope section."""
        slug = "sync_scope"
        _create_test_plan(tmp_settings, slug, [
            ("Verify", [
                {"number": 1, "title": "Verify Task", "subtasks": [("1.1", "Sub 1.1")]},
            ]),
        ])

        plan_sync(slug, 0, 1, tmp_settings)
        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_verify.md"
        content = phase_file.read_text()
        assert "- [ ] Scope checkbox that should NOT be toggled" in content

    def test_does_not_modify_reviewer_checklist(self, tmp_settings):
        """7.6: plan_sync does NOT modify checkboxes in Reviewer Checklist."""
        slug = "sync_checklist"
        _create_test_plan(tmp_settings, slug, [
            ("Review", [
                {"number": 1, "title": "Review Task", "subtasks": [("1.1", "Sub 1.1")]},
            ]),
        ])

        plan_sync(slug, 0, 1, tmp_settings)
        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_review.md"
        content = phase_file.read_text()
        # Reviewer checklist checkboxes should be untouched
        assert "- [ ] All top-level tasks use" in content
        assert "- [ ] All sub-tasks use" in content

    def test_does_not_modify_code_fences(self, tmp_settings):
        """7.7: plan_sync does NOT modify checkboxes inside code fences."""
        slug = "sync_fence"
        plan_dir = tmp_settings.active_plans_dir / slug
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True, exist_ok=True)

        # Create a phase file with code fence containing checkbox-like lines
        content = """# Phase 0: Fence Test

**Status:** Pending

---

## Detailed Objective

Test.

## Deliverables Snapshot

1. One.

## Acceptance Gates

- [ ] Gate 1: test

## Scope

In scope.

## Interfaces & Dependencies

None.

## Risks & Mitigations

None.

## Decision Log

None.

## References

### Source Files

None.

### Destination Files

None.

### Related Documentation

None.

## Tasks

```markdown
### [ ] 1 Example Inside Fence
  - [ ] 1.1 Should NOT be toggled
```

### [ ] 1 Real Task Outside Fence
Description.

  - [ ] 1.1 Real Subtask

## Completion Step (Required)

Done.

## Reviewer Checklist

### Structure

- [ ] All good.
"""
        phase_file = phases_dir / "phase_0_fence_test.md"
        phase_file.write_text(content)
        _create_master_plan(plan_dir, slug, [(0, "Fence Test")])

        plan_sync(slug, 0, 1, tmp_settings)

        new_content = phase_file.read_text()
        # The real task should be toggled
        assert "### [\u2705] 1 Real Task Outside Fence" in new_content
        assert "[\u2705] 1.1 Real Subtask" in new_content
        # The code fence content should be untouched
        assert "### [ ] 1 Example Inside Fence" in new_content
        assert "  - [ ] 1.1 Should NOT be toggled" in new_content

    def test_idempotent(self, tmp_settings):
        """7.8: Calling plan_sync twice produces same file content."""
        slug = "sync_idempotent"
        _create_test_plan(tmp_settings, slug, [
            ("Idempotent", [
                {"number": 1, "title": "Task One", "subtasks": [("1.1", "Sub")]},
            ]),
        ])

        result1 = plan_sync(slug, 0, 1, tmp_settings)
        assert result1.checkmarks_toggled > 0

        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_idempotent.md"
        content_after_first = phase_file.read_text()

        result2 = plan_sync(slug, 0, 1, tmp_settings)
        assert result2.checkmarks_toggled == 0
        assert result2.details == ["Task already marked complete"]

        content_after_second = phase_file.read_text()
        assert content_after_first == content_after_second

    def test_dry_run_no_modification(self, tmp_settings):
        """7.9: plan_sync --dry-run returns correct SyncResult but file unchanged."""
        slug = "sync_dryrun"
        _create_test_plan(tmp_settings, slug, [
            ("DryRun", [
                {"number": 1, "title": "DryRun Task", "subtasks": [("1.1", "Sub")]},
            ]),
        ])

        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_dryrun.md"
        hash_before = hashlib.sha256(phase_file.read_bytes()).hexdigest()

        result = plan_sync(slug, 0, 1, tmp_settings, dry_run=True)
        assert result.dry_run is True
        assert result.checkmarks_toggled > 0

        hash_after = hashlib.sha256(phase_file.read_bytes()).hexdigest()
        assert hash_before == hash_after

    def test_nonexistent_task_raises_value_error(self, tmp_settings):
        """7.10: plan_sync for nonexistent task raises ValueError."""
        slug = "sync_missing"
        _create_test_plan(tmp_settings, slug, [
            ("Missing", [
                {"number": 1, "title": "Only Task", "subtasks": []},
            ]),
        ])

        with pytest.raises(ValueError, match="Task 99 not found"):
            plan_sync(slug, 0, 99, tmp_settings)

    def test_atomic_write_on_failure(self, tmp_settings):
        """7.11: If os.replace raises, original file is not corrupted."""
        slug = "sync_atomic"
        _create_test_plan(tmp_settings, slug, [
            ("Atomic", [
                {"number": 1, "title": "Atomic Task", "subtasks": [("1.1", "Sub")]},
            ]),
        ])

        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_atomic.md"
        original_content = phase_file.read_text()

        with patch("orchestrator_v3.plan_tool.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                plan_sync(slug, 0, 1, tmp_settings)

        # Original file should be intact
        assert phase_file.read_text() == original_content


# ---------------------------------------------------------------------------
# Test 8: plan_render_master and plan_reconcile unit tests
# ---------------------------------------------------------------------------


class TestPlanRenderMaster:
    """Unit tests for plan_render_master()."""

    def test_produces_correct_overview(self, tmp_settings):
        """8.1: plan_render_master produces Phases Overview with task headings and subtasks only."""
        slug = "render_master"
        _create_test_plan(tmp_settings, slug, [
            ("Setup", [
                {"number": 1, "title": "Init", "subtasks": [("1.1", "Config")]},
                {"number": 2, "title": "Build", "subtasks": [("2.1", "Compile")]},
            ]),
            ("Deploy", [
                {"number": 1, "title": "Release", "subtasks": [("1.1", "Publish")]},
            ]),
        ])

        result = plan_render_master(slug, tmp_settings)
        assert result.files_updated == 1
        assert result.checkmarks_toggled > 0

        master_file = tmp_settings.active_plans_dir / slug / f"{slug}_master_plan.md"
        content = master_file.read_text()

        # Check task headings appear
        assert "### [ ] 1 Init" in content
        assert "### [ ] 2 Build" in content
        assert "### [ ] 1 Release" in content
        # Check subtasks appear
        assert "  - [ ] 1.1 Config" in content
        assert "  - [ ] 2.1 Compile" in content
        assert "  - [ ] 1.1 Publish" in content
        # Check phase headers
        assert "### Phase 0: Setup" in content
        assert "### Phase 1: Deploy" in content

    def test_matches_expected_output(self, tmp_settings):
        """8.2: plan_render_master result matches manually constructed expected output."""
        slug = "render_exact"
        # Mark task 1 in phase 0 as checked, others unchecked
        _create_test_plan(tmp_settings, slug, [
            ("Alpha", [
                {"number": 1, "title": "Task A1", "subtasks": [("1.1", "Sub A1.1")], "checked": True},
                {"number": 2, "title": "Task A2", "subtasks": [("2.1", "Sub A2.1")]},
            ]),
            ("Beta", [
                {"number": 1, "title": "Task B1", "subtasks": [("1.1", "Sub B1.1")]},
            ]),
        ])

        plan_render_master(slug, tmp_settings)
        master_file = tmp_settings.active_plans_dir / slug / f"{slug}_master_plan.md"
        content = master_file.read_text()

        # Task A1 should show as checked, A2 and B1 as unchecked
        assert "### [\u2705] 1 Task A1" in content
        assert "### [ ] 2 Task A2" in content
        assert "### [ ] 1 Task B1" in content

    def test_preserves_content_outside_overview(self, tmp_settings):
        """8.3: plan_render_master preserves content outside Phases Overview."""
        slug = "render_preserve"
        _create_test_plan(tmp_settings, slug, [
            ("Only", [
                {"number": 1, "title": "One Task", "subtasks": []},
            ]),
        ])

        master_file = tmp_settings.active_plans_dir / slug / f"{slug}_master_plan.md"
        original = master_file.read_text()

        plan_render_master(slug, tmp_settings)
        updated = master_file.read_text()

        # Executive Summary should be preserved
        assert "## Executive Summary" in updated
        assert "Test master plan." in updated
        # Decision Log should be preserved
        assert "## Decision Log" in updated
        # Reviewer Checklist should be preserved
        assert "## Reviewer Checklist" in updated

    def test_dry_run_no_modification(self, tmp_settings):
        """8.4: plan_render_master --dry-run does not modify the master file."""
        slug = "render_dryrun"
        _create_test_plan(tmp_settings, slug, [
            ("Test", [
                {"number": 1, "title": "Task", "subtasks": []},
            ]),
        ])

        master_file = tmp_settings.active_plans_dir / slug / f"{slug}_master_plan.md"
        hash_before = hashlib.sha256(master_file.read_bytes()).hexdigest()

        result = plan_render_master(slug, tmp_settings, dry_run=True)
        assert result.dry_run is True

        hash_after = hashlib.sha256(master_file.read_bytes()).hexdigest()
        assert hash_before == hash_after


class TestPlanReconcile:
    """Unit tests for plan_reconcile()."""

    def test_detects_missing_in_plan(self, tmp_settings):
        """8.5: Detects drift when state has approved but plan is unchecked."""
        slug = "reconcile_missing_plan"
        _create_test_plan(tmp_settings, slug, [
            ("Setup", [
                {"number": 1, "title": "Task 1", "subtasks": []},
                {"number": 2, "title": "Task 2", "subtasks": []},
            ]),
        ])
        # Mark task 1 as approved in state
        _create_task_state(tmp_settings, slug, phase=0, task=1, status=Status.APPROVED)

        report = plan_reconcile(slug, tmp_settings)
        assert not report.in_sync
        assert (0, 1) in report.missing_in_plan
        assert (0, 1) in report.state_completed

    def test_detects_missing_in_state(self, tmp_settings):
        """8.6: Detects reverse drift when plan is checked but state is not approved."""
        slug = "reconcile_missing_state"
        _create_test_plan(tmp_settings, slug, [
            ("Setup", [
                {"number": 1, "title": "Task 1", "subtasks": [], "checked": True},
                {"number": 2, "title": "Task 2", "subtasks": []},
            ]),
        ])
        # No task state files — task 1 is checked in plan but not in state

        report = plan_reconcile(slug, tmp_settings)
        assert not report.in_sync
        assert (0, 1) in report.missing_in_state
        assert (0, 1) in report.plan_completed

    def test_in_sync(self, tmp_settings):
        """8.7: Reports in_sync=True when state and plan agree."""
        slug = "reconcile_sync"
        _create_test_plan(tmp_settings, slug, [
            ("Match", [
                {"number": 1, "title": "Done Task", "subtasks": [], "checked": True},
                {"number": 2, "title": "Pending Task", "subtasks": []},
            ]),
        ])
        # Mark task 1 as approved
        _create_task_state(tmp_settings, slug, phase=0, task=1, status=Status.APPROVED)

        report = plan_reconcile(slug, tmp_settings)
        assert report.in_sync
        assert len(report.missing_in_plan) == 0
        assert len(report.missing_in_state) == 0

    def test_apply_fixes_drift(self, tmp_settings):
        """8.8: plan_reconcile --apply calls plan_sync for missing entries."""
        slug = "reconcile_apply"
        _create_test_plan(tmp_settings, slug, [
            ("Fix", [
                {"number": 1, "title": "Fix Task", "subtasks": [("1.1", "Sub")]},
                {"number": 2, "title": "Other Task", "subtasks": []},
            ]),
        ])
        _create_task_state(tmp_settings, slug, phase=0, task=1, status=Status.APPROVED)

        report = plan_reconcile(slug, tmp_settings, apply=True)
        assert (0, 1) in report.missing_in_plan

        # After apply, the plan should be updated
        phase_file = tmp_settings.active_plans_dir / slug / "phases" / "phase_0_fix.md"
        content = phase_file.read_text()
        assert "### [\u2705] 1 Fix Task" in content

    def test_from_reviews_infers_approval(self, tmp_settings):
        """8.9: plan_reconcile --from-reviews adds tasks from APPROVED review files."""
        slug = "reconcile_reviews"
        _create_test_plan(tmp_settings, slug, [
            ("Review", [
                {"number": 1, "title": "Reviewed Task", "subtasks": []},
                {"number": 2, "title": "Unreviewed Task", "subtasks": []},
            ]),
        ])
        # Create a review file with APPROVED verdict (no per-task state file)
        _create_review_file(tmp_settings, slug, phase=0, task=1, round_num=3, verdict="APPROVED")

        report = plan_reconcile(slug, tmp_settings, from_reviews=True)
        assert (0, 1) in report.state_completed
        assert (0, 1) in report.missing_in_plan


# ---------------------------------------------------------------------------
# Test 9: Integration tests against empirical data
# ---------------------------------------------------------------------------


class TestEmpiricalIntegration:
    """Integration tests using real triton plan and state data."""

    @pytest.mark.skipif(not HAS_EMPIRICAL, reason="Empirical data not available")
    def test_reconcile_gpu_saturation(self, tmp_settings):
        """9.1: plan_reconcile against gpu_saturation_benchmark."""
        import shutil

        slug = "gpu_saturation_benchmark"
        # Copy plans to tmp active_plans
        src_plans = TRITON_PLANS / slug
        dst_plans = tmp_settings.active_plans_dir / slug
        shutil.copytree(src_plans, dst_plans)

        # Copy state files to tmp reviews
        state_re = re.compile(rf"^{re.escape(slug)}_p(\d+)_t(\d+)_state\.json$")
        approved_pairs = set()
        for f in TRITON_REVIEWS.iterdir():
            m = state_re.match(f.name)
            if m:
                shutil.copy2(f, tmp_settings.reviews_dir / f.name)
                # Read to check if approved
                data = json.loads(f.read_text())
                if data.get("status") == "approved":
                    approved_pairs.add((int(m.group(1)), int(m.group(2))))

        report = plan_reconcile(slug, tmp_settings)
        # All approved tasks should be in missing_in_plan (since plans are stale/unchecked)
        assert report.missing_in_plan.issuperset(approved_pairs)

    @pytest.mark.skipif(not HAS_EMPIRICAL, reason="Empirical data not available")
    def test_reconcile_all_triton_plans(self, tmp_settings):
        """9.2: plan_reconcile across all 4 triton plans."""
        import shutil

        total_approved = 0
        total_missing_in_plan = 0

        for plan_dir in TRITON_PLANS.iterdir():
            if not plan_dir.is_dir() or not (plan_dir / "phases").is_dir():
                continue

            slug = plan_dir.name
            dst_plans = tmp_settings.active_plans_dir / slug
            shutil.copytree(plan_dir, dst_plans)

            # Copy state files
            state_re = re.compile(rf"^{re.escape(slug)}_p(\d+)_t(\d+)_state\.json$")
            for f in TRITON_REVIEWS.iterdir():
                m = state_re.match(f.name)
                if m:
                    dst = tmp_settings.reviews_dir / f.name
                    if not dst.exists():
                        shutil.copy2(f, dst)
                    data = json.loads(f.read_text())
                    if data.get("status") == "approved":
                        total_approved += 1

            report = plan_reconcile(slug, tmp_settings)
            total_missing_in_plan += len(report.missing_in_plan)

        assert total_missing_in_plan == total_approved

    @pytest.mark.skipif(not HAS_EMPIRICAL, reason="Empirical data not available")
    def test_reconcile_apply_then_verify(self, tmp_settings):
        """9.3: Apply fixes to triton plans, then verify in_sync."""
        import shutil

        slug = "gpu_saturation_benchmark"
        src_plans = TRITON_PLANS / slug
        dst_plans = tmp_settings.active_plans_dir / slug
        shutil.copytree(src_plans, dst_plans)

        # Copy state files
        state_re = re.compile(rf"^{re.escape(slug)}_p(\d+)_t(\d+)_state\.json$")
        for f in TRITON_REVIEWS.iterdir():
            m = state_re.match(f.name)
            if m:
                shutil.copy2(f, tmp_settings.reviews_dir / f.name)

        # Apply
        plan_reconcile(slug, tmp_settings, apply=True)

        # Re-reconcile should be in sync
        report2 = plan_reconcile(slug, tmp_settings)
        assert report2.in_sync

    @pytest.mark.skipif(not HAS_EMPIRICAL, reason="Empirical data not available")
    def test_reconcile_from_reviews_triton(self, tmp_settings):
        """9.4: plan_reconcile --from-reviews on triton data."""
        import shutil

        slug = "gpu_saturation_benchmark"
        src_plans = TRITON_PLANS / slug
        dst_plans = tmp_settings.active_plans_dir / slug
        shutil.copytree(src_plans, dst_plans)

        # Copy review files AND state files
        for f in TRITON_REVIEWS.iterdir():
            if f.name.startswith(slug) and f.suffix == ".md":
                shutil.copy2(f, tmp_settings.reviews_dir / f.name)
            if f.name.startswith(slug) and f.name.endswith("_state.json"):
                shutil.copy2(f, tmp_settings.reviews_dir / f.name)

        report = plan_reconcile(slug, tmp_settings, from_reviews=True)
        # from_reviews should find at least as many as state-only
        report_state_only = plan_reconcile(slug, tmp_settings)
        assert report.state_completed.issuperset(report_state_only.state_completed)

    @pytest.mark.skipif(not HAS_EMPIRICAL, reason="Empirical data not available")
    def test_render_master_after_apply(self, tmp_settings):
        """9.5: plan_render_master after apply produces well-formed overview."""
        import shutil

        slug = "gpu_saturation_benchmark"
        src_plans = TRITON_PLANS / slug
        dst_plans = tmp_settings.active_plans_dir / slug
        shutil.copytree(src_plans, dst_plans)

        # Copy state files
        for f in TRITON_REVIEWS.iterdir():
            if f.name.startswith(slug) and f.name.endswith("_state.json"):
                shutil.copy2(f, tmp_settings.reviews_dir / f.name)

        plan_reconcile(slug, tmp_settings, apply=True)
        plan_render_master(slug, tmp_settings)

        master_file = dst_plans / f"{slug}_master_plan.md"
        content = master_file.read_text()
        # Should have phase headings
        task_headings = re.findall(r"^### \[.\] \d+ ", content, re.MULTILINE)
        assert len(task_headings) > 0

    @pytest.mark.skipif(not HAS_CASTLEGUARD, reason="TitanAI castleguard not available")
    def test_sync_castleguard(self, tmp_settings):
        """9.6: plan_sync on TitanAI castleguard preserves other content."""
        import shutil

        slug = "castleguard_modernization"
        dst_plans = tmp_settings.active_plans_dir / slug
        shutil.copytree(CASTLEGUARD_DIR, dst_plans)

        phases_dir = dst_plans / "phases"
        if not phases_dir.is_dir():
            pytest.skip("No phases/ directory in castleguard plan")

        phase_files = sorted(phases_dir.glob("phase_*.md"))
        if not phase_files:
            pytest.skip("No phase files found")

        # Pick first phase file, find first unchecked task
        phase_file = phase_files[0]
        original_content = phase_file.read_text()

        from orchestrator_v3.plan_tool import PlanParser

        parser = PlanParser(original_content, str(phase_file), PlanType.COMPLEX)
        parsed = parser.parse()
        unchecked = [t for t in parsed.tasks if t.level == "top" and not t.checked]
        if not unchecked:
            pytest.skip("All tasks already checked")

        target_task = int(unchecked[0].number)
        m = re.search(r"phase_(\d+)_", phase_file.name)
        phase_num = int(m.group(1)) if m else 0

        result = plan_sync(slug, phase_num, target_task, tmp_settings)
        assert result.checkmarks_toggled >= 1

        new_content = phase_file.read_text()
        # The target task should be checked
        assert f"### [\u2705] {target_task} " in new_content
        # Other unchanged lines should be identical
        original_lines = original_content.splitlines()
        new_lines = new_content.splitlines()
        changed_count = sum(1 for a, b in zip(original_lines, new_lines) if a != b)
        assert changed_count == result.checkmarks_toggled


# ---------------------------------------------------------------------------
# Test 10: Auto-trigger tests
# ---------------------------------------------------------------------------


class TestAutoTrigger:
    """Tests for auto-trigger integration in handle_approval()."""

    def _build_mock_loop(self, tmp_settings, slug, phase, task, plan_type=PlanType.COMPLEX):
        """Build a minimal OrchestratorLoop mock for testing handle_approval."""
        from orchestrator_v3.loop import OrchestratorLoop

        # Create plan structure
        if plan_type == PlanType.COMPLEX:
            _create_test_plan(tmp_settings, slug, [
                ("Test", [
                    {"number": 1, "title": "Task One", "subtasks": [("1.1", "Sub")]},
                    {"number": 2, "title": "Task Two", "subtasks": [("2.1", "Sub")]},
                ]),
            ])
        else:
            # Simple plan
            plan_file = tmp_settings.active_plans_dir / f"{slug}.md"
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_file.write_text("# Simple Plan\n\n## Tasks\n\n### [ ] 1 Task\n")

        # Create campaign index
        cm = CampaignManager(
            state_path=campaign_index_path(slug, tmp_settings),
            settings=tmp_settings,
        )
        cm.init(
            slug=slug,
            mode=Mode.CODE,
            plan_file=f"active_plans/{slug}/{slug}_master_plan.md",
            total_phases=1,
            tasks_per_phase={"0": 2},
            current_phase=phase,
            current_task=task,
        )

        # Create per-task state
        _create_task_state(tmp_settings, slug, phase, task, status=Status.NEEDS_REVIEW)

        # Build mock objects
        mock_ar = MagicMock()
        mock_ar.slug = slug
        mock_ar.phase = phase
        mock_ar.task = task
        mock_ar.detect_plan_type.return_value = plan_type

        mock_tsm = TaskStateManager(
            state_path=task_state_path(slug, phase, task, tmp_settings)
        )

        mock_display = MagicMock()
        mock_pb = MagicMock()
        mock_reviewer = MagicMock()

        loop = OrchestratorLoop(
            state_manager=mock_tsm,
            artifact_resolver=mock_ar,
            prompt_builder=mock_pb,
            reviewer=mock_reviewer,
            display=mock_display,
            settings=tmp_settings,
            campaign_manager=cm,
        )

        return loop

    def test_fires_on_code_mode_approval(self, tmp_settings):
        """10.1: Auto-trigger fires on code-mode approval with correct arguments."""
        slug = "trigger_code"
        loop = self._build_mock_loop(tmp_settings, slug, 0, 1)

        with patch("orchestrator_v3.plan_tool.plan_sync") as mock_sync, \
             patch("orchestrator_v3.plan_tool.plan_render_master") as mock_render:
            loop.handle_approval(round_num=1)

            mock_sync.assert_called_once_with(
                slug=slug,
                phase=0,
                task=1,
                settings=tmp_settings,
            )
            mock_render.assert_called_once_with(
                slug=slug,
                settings=tmp_settings,
            )

    def test_fires_plan_sync_and_render_for_complex(self, tmp_settings):
        """10.2: Both plan_sync and plan_render_master called for complex plan."""
        slug = "trigger_complex"
        loop = self._build_mock_loop(tmp_settings, slug, 0, 1)

        with patch("orchestrator_v3.plan_tool.plan_sync") as mock_sync, \
             patch("orchestrator_v3.plan_tool.plan_render_master") as mock_render:
            loop.handle_approval(round_num=1)

            assert mock_sync.called
            assert mock_render.called

    def test_skips_simple_plans(self, tmp_settings):
        """10.3: Auto-trigger does NOT fire for simple plans."""
        slug = "trigger_simple"
        loop = self._build_mock_loop(tmp_settings, slug, 0, 1, plan_type=PlanType.SIMPLE)

        with patch("orchestrator_v3.plan_tool.plan_sync") as mock_sync, \
             patch("orchestrator_v3.plan_tool.plan_render_master") as mock_render:
            loop.handle_approval(round_num=1)

            mock_sync.assert_not_called()
            mock_render.assert_not_called()

    def test_nonfatal_sync_error(self, tmp_settings):
        """10.4: plan_sync RuntimeError does not block handle_approval()."""
        slug = "trigger_nonfatal_sync"
        loop = self._build_mock_loop(tmp_settings, slug, 0, 1)

        with patch("orchestrator_v3.plan_tool.plan_sync", side_effect=RuntimeError("sync failed")):
            # Should NOT raise — sync failure is non-fatal
            loop.handle_approval(round_num=1)

        # Campaign should have advanced
        cm = CampaignManager(
            state_path=campaign_index_path(slug, tmp_settings),
            settings=tmp_settings,
        )
        ci = cm.load()
        # Task should have advanced past task 1
        assert ci.current_task == 2 or ci.status in ("complete", "needs_review")

    def test_nonfatal_render_error(self, tmp_settings):
        """10.5: plan_render_master OSError does not block handle_approval()."""
        slug = "trigger_nonfatal_render"
        loop = self._build_mock_loop(tmp_settings, slug, 0, 1)

        with patch("orchestrator_v3.plan_tool.plan_sync") as mock_sync, \
             patch("orchestrator_v3.plan_tool.plan_render_master", side_effect=OSError("disk full")):
            mock_sync.return_value = SyncResult(files_updated=1, checkmarks_toggled=1)
            # Should NOT raise — render failure is non-fatal
            loop.handle_approval(round_num=1)

        # Campaign should have advanced
        cm = CampaignManager(
            state_path=campaign_index_path(slug, tmp_settings),
            settings=tmp_settings,
        )
        ci = cm.load()
        assert ci.current_task == 2 or ci.status in ("complete", "needs_review")

    def test_does_not_fire_in_plan_mode(self, tmp_settings):
        """10.6: Auto-trigger does NOT fire for plan-mode approvals."""
        from orchestrator_v3.loop import OrchestratorLoop
        from orchestrator_v3.state import StateManager

        slug = "trigger_planmode"
        plan_file = tmp_settings.active_plans_dir / f"{slug}.md"
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        plan_file.write_text("# Plan\n## Tasks\n### [ ] 1 Task\n")

        state_path = tmp_settings.reviews_dir / f"{slug}_orchestrator_state.json"
        sm = StateManager(state_path=state_path, settings=tmp_settings)
        sm.init(
            plan_slug=slug,
            mode=Mode.PLAN,
            plan_file=str(plan_file),
            plan_type=PlanType.SIMPLE,
        )

        mock_ar = MagicMock()
        mock_ar.slug = slug
        mock_ar.phase = 0
        mock_ar.task = 1

        loop = OrchestratorLoop(
            state_manager=sm,
            artifact_resolver=mock_ar,
            prompt_builder=MagicMock(),
            reviewer=MagicMock(),
            display=MagicMock(),
            settings=tmp_settings,
            campaign_manager=None,
        )

        with patch("orchestrator_v3.plan_tool.plan_sync") as mock_sync, \
             patch("orchestrator_v3.plan_tool.plan_render_master") as mock_render:
            loop.handle_approval(round_num=1)

            mock_sync.assert_not_called()
            mock_render.assert_not_called()

    def test_does_not_fire_without_campaign_manager(self, tmp_settings):
        """10.7: Auto-trigger does NOT fire when campaign_manager is None."""
        from orchestrator_v3.loop import OrchestratorLoop
        from orchestrator_v3.state import TaskStateManager

        slug = "trigger_nocm"
        _create_test_plan(tmp_settings, slug, [
            ("Only", [
                {"number": 1, "title": "Task One", "subtasks": []},
            ]),
        ])

        # Create per-task state as code mode
        ts_path = task_state_path(slug, 0, 1, tmp_settings)
        tsm = TaskStateManager(state_path=ts_path)
        tsm.init(slug=slug, phase=0, task=1, plan_file="test.md", mode=Mode.CODE)

        mock_ar = MagicMock()
        mock_ar.slug = slug
        mock_ar.phase = 0
        mock_ar.task = 1

        loop = OrchestratorLoop(
            state_manager=tsm,
            artifact_resolver=mock_ar,
            prompt_builder=MagicMock(),
            reviewer=MagicMock(),
            display=MagicMock(),
            settings=tmp_settings,
            campaign_manager=None,  # No campaign manager
        )

        with patch("orchestrator_v3.plan_tool.plan_sync") as mock_sync, \
             patch("orchestrator_v3.plan_tool.plan_render_master") as mock_render:
            loop.handle_approval(round_num=1)

            # Without campaign_manager, auto-trigger should not fire
            mock_sync.assert_not_called()
            mock_render.assert_not_called()


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestSyncResultModel:
    def test_summary_default(self):
        r = SyncResult(files_updated=1, checkmarks_toggled=3)
        s = r.summary()
        assert "1 file(s) updated" in s
        assert "3 checkmark(s) toggled" in s
        assert "[DRY RUN]" not in s

    def test_summary_dry_run(self):
        r = SyncResult(files_updated=1, checkmarks_toggled=3, dry_run=True)
        assert "[DRY RUN]" in r.summary()


class TestDriftReportModel:
    def test_summary_in_sync(self):
        r = DriftReport(in_sync=True)
        assert "In sync" in r.summary()

    def test_summary_drift(self):
        r = DriftReport(
            in_sync=False,
            missing_in_plan=frozenset({(0, 1), (1, 2)}),
            missing_in_state=frozenset({(2, 3)}),
        )
        s = r.summary()
        assert "DRIFT" in s
        assert "p0, t1" in s
        assert "p2, t3" in s
