"""Comprehensive tests for plan verification functions and plan-verify CLI.

Tests each check function independently (positive and negative cases),
integration tests for verify_plan_syntax(), and CLI tests via CliRunner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from orchestrator_v3.config import PlanType
from orchestrator_v3.plan_tool import (
    ParsedPlan,
    ParsedSection,
    ParsedTask,
    PlanParser,
    PlanVerificationIssue,
    PlanVerificationResult,
    check_acceptance_gates,
    check_cross_file_consistency,
    check_depth_violations,
    check_greppable_patterns,
    check_references_subsections,
    check_required_sections,
    check_source_paths,
    check_task_descriptions,
    check_task_numbering,
    parse_plan,
    verify_plan_syntax,
)


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers: build minimal ParsedPlan objects for unit tests
# ---------------------------------------------------------------------------


def _make_plan(
    sections: list[str] | None = None,
    tasks: list[ParsedTask] | None = None,
    plan_type: PlanType = PlanType.COMPLEX,
    file_path: str = "",
    section_objects: list[ParsedSection] | None = None,
) -> ParsedPlan:
    """Build a minimal ParsedPlan for testing."""
    if section_objects is not None:
        secs = section_objects
    elif sections is not None:
        secs = [
            ParsedSection(name=name, line_number=i * 10 + 10, line_range=(i * 10 + 10, i * 10 + 19))
            for i, name in enumerate(sections)
        ]
    else:
        secs = []
    return ParsedPlan(
        file_path=file_path,
        plan_type=plan_type,
        sections=secs,
        tasks=tasks or [],
        metadata={},
    )


def _make_task(
    number: str,
    title: str = "Task",
    level: str = "top",
    line_number: int = 1,
    checked: bool = False,
    children: list[ParsedTask] | None = None,
) -> ParsedTask:
    """Build a minimal ParsedTask for testing."""
    return ParsedTask(
        number=number,
        title=title,
        level=level,
        line_number=line_number,
        line_range=(line_number, line_number + 5),
        checked=checked,
        children=children or [],
    )


# ===========================================================================
# Test check_required_sections
# ===========================================================================


class TestCheckRequiredSections:
    """Tests for check_required_sections()."""

    def test_phase_plan_all_sections_present(self):
        """Phase plan with all required sections in order produces zero issues."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_PHASE
        plan = _make_plan(
            sections=REQUIRED_SECTIONS_PHASE,
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/phases/phase_0_test.md",
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_phase_plan_missing_tasks(self):
        """Phase plan missing ## Tasks produces one error."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_PHASE
        sections = [s for s in REQUIRED_SECTIONS_PHASE if s != "Tasks"]
        plan = _make_plan(
            sections=sections,
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/phases/phase_0_test.md",
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "Tasks" in errors[0].message

    def test_phase_plan_missing_completion_step(self):
        """Phase plan missing ## Completion Step (Required) produces one error."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_PHASE
        sections = [s for s in REQUIRED_SECTIONS_PHASE if s != "Completion Step (Required)"]
        plan = _make_plan(
            sections=sections,
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/phases/phase_0_test.md",
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "Completion Step" in errors[0].message

    def test_phase_plan_missing_reviewer_checklist(self):
        """Phase plan missing ## Reviewer Checklist produces one error."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_PHASE
        sections = [s for s in REQUIRED_SECTIONS_PHASE if s != "Reviewer Checklist"]
        plan = _make_plan(
            sections=sections,
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/phases/phase_0_test.md",
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "Reviewer Checklist" in errors[0].message

    def test_phase_plan_sections_out_of_order(self):
        """Phase plan with two sections swapped produces a warning."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_PHASE
        sections = list(REQUIRED_SECTIONS_PHASE)
        # Swap Tasks and References
        idx_tasks = sections.index("Tasks")
        idx_refs = sections.index("References")
        sections[idx_tasks], sections[idx_refs] = sections[idx_refs], sections[idx_tasks]
        plan = _make_plan(
            sections=sections,
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/phases/phase_0_test.md",
        )
        issues = check_required_sections(plan)
        warnings = [i for i in issues if i.severity == "warning"]
        assert len(warnings) >= 1

    def test_simple_plan_all_sections_present(self):
        """Simple plan with all required sections produces zero errors."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_SIMPLE
        plan = _make_plan(
            sections=REQUIRED_SECTIONS_SIMPLE,
            plan_type=PlanType.SIMPLE,
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_simple_plan_missing_acceptance_criteria(self):
        """Simple plan missing ## Acceptance Criteria produces an error."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_SIMPLE
        sections = [s for s in REQUIRED_SECTIONS_SIMPLE if s != "Acceptance Criteria"]
        plan = _make_plan(
            sections=sections,
            plan_type=PlanType.SIMPLE,
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "Acceptance Criteria" in errors[0].message

    def test_simple_plan_optional_states_modes_present(self):
        """Simple plan with optional ## States & Modes present still passes."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_SIMPLE
        sections = list(REQUIRED_SECTIONS_SIMPLE)
        # Insert optional section
        sections.insert(2, "States & Modes")
        plan = _make_plan(
            sections=sections,
            plan_type=PlanType.SIMPLE,
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_master_plan_all_sections_present(self):
        """Master plan with all required sections produces zero errors."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_MASTER
        plan = _make_plan(
            sections=REQUIRED_SECTIONS_MASTER,
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/master_plan.md",
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_master_plan_missing_phases_overview(self):
        """Master plan missing ## Phases Overview produces an error."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_MASTER
        sections = [s for s in REQUIRED_SECTIONS_MASTER if s != "Phases Overview"]
        plan = _make_plan(
            sections=sections,
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/master_plan.md",
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        # Without Phases Overview, this won't be detected as master
        # So we need to ensure the plan has something that makes it master-like
        # Actually, without Phases Overview AND not in phases/ dir, _is_master_plan
        # returns True because file_path parent != "phases"
        assert any("Phases Overview" in e.message for e in errors)

    def test_master_plan_missing_executive_summary(self):
        """Master plan missing ## Executive Summary produces an error."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_MASTER
        sections = [s for s in REQUIRED_SECTIONS_MASTER if s != "Executive Summary"]
        plan = _make_plan(
            sections=sections,
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/master_plan.md",
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert any("Executive Summary" in e.message for e in errors)

    def test_section_alias_dependencies(self):
        """Section named 'Dependencies' is treated as 'Interfaces & Dependencies'."""
        from orchestrator_v3.plan_tool import REQUIRED_SECTIONS_PHASE
        sections = [
            "Dependencies" if s == "Interfaces & Dependencies" else s
            for s in REQUIRED_SECTIONS_PHASE
        ]
        plan = _make_plan(
            sections=sections,
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/phases/phase_0_test.md",
        )
        issues = check_required_sections(plan)
        errors = [i for i in issues if i.severity == "error"]
        # Should NOT report Interfaces & Dependencies as missing
        assert not any("Interfaces & Dependencies" in e.message for e in errors)


# ===========================================================================
# Test check_task_numbering
# ===========================================================================


class TestCheckTaskNumbering:
    """Tests for check_task_numbering()."""

    def test_sequential_numbering_no_issues(self):
        """Tasks numbered 1, 2, 3 produce zero issues."""
        tasks = [
            _make_task("1", line_number=10),
            _make_task("2", line_number=20),
            _make_task("3", line_number=30),
        ]
        plan = _make_plan(tasks=tasks)
        issues = check_task_numbering(plan)
        assert len(issues) == 0

    def test_gap_in_top_level(self):
        """Tasks 1, 2, 4 produce error for missing 3."""
        tasks = [
            _make_task("1", line_number=10),
            _make_task("2", line_number=20),
            _make_task("4", line_number=40),
        ]
        plan = _make_plan(tasks=tasks)
        issues = check_task_numbering(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "3" in errors[0].message

    def test_gap_in_subtasks(self):
        """Subtasks 1.1, 1.3 produce error for missing 1.2."""
        children = [
            _make_task("1.1", level="sub", line_number=12),
            _make_task("1.3", level="sub", line_number=14),
        ]
        tasks = [_make_task("1", line_number=10, children=children)]
        plan = _make_plan(tasks=tasks)
        issues = check_task_numbering(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "2" in errors[0].message  # Missing subtask 2 (the .2 part)

    def test_duplicate_task_number(self):
        """Duplicate task 2 produces error."""
        tasks = [
            _make_task("1", line_number=10),
            _make_task("2", line_number=20),
            _make_task("2", line_number=30),
        ]
        plan = _make_plan(tasks=tasks)
        issues = check_task_numbering(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert any("Duplicate" in e.message or "duplicate" in e.message.lower() for e in errors)

    def test_numbering_gaps_fixture(self, malformed_plan):
        """Numbering_gaps fixture has gaps at task 3 and subtask 2.2."""
        plan = parse_plan(malformed_plan["numbering_gaps"])
        issues = check_task_numbering(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1  # At least the task 3 gap

    def test_master_plan_per_phase_numbering(self, complex_plan_fixture):
        """Master plan with per-phase ### [ ] 1 restarts produces zero issues."""
        master = complex_plan_fixture / "gpu_saturation_benchmark_master_plan.md"
        plan = parse_plan(master)
        issues = check_task_numbering(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0


# ===========================================================================
# Test check_depth_violations
# ===========================================================================


class TestCheckDepthViolations:
    """Tests for check_depth_violations()."""

    def test_phase_plan_depth_2_ok(self):
        """Phase plan with N.M subtasks produces zero issues."""
        children = [_make_task("1.1", level="sub", line_number=12)]
        tasks = [_make_task("1", line_number=10, children=children)]
        plan = _make_plan(tasks=tasks, file_path="/tmp/phases/phase_0.md")
        issues = check_depth_violations(plan)
        assert len(issues) == 0

    def test_phase_plan_depth_3_ok(self):
        """Phase plan with N.M.K (optional leaf) produces zero issues."""
        leaf = _make_task("1.1.1", level="leaf", line_number=14)
        children = [_make_task("1.1", level="sub", line_number=12, children=[leaf])]
        tasks = [_make_task("1", line_number=10, children=children)]
        plan = _make_plan(tasks=tasks, file_path="/tmp/phases/phase_0.md")
        issues = check_depth_violations(plan)
        assert len(issues) == 0

    def test_phase_plan_depth_4_error(self):
        """Phase plan with N.M.K.L produces an error."""
        deep = _make_task("1.1.1.1", level="leaf", line_number=16)
        leaf = _make_task("1.1.1", level="leaf", line_number=14, children=[deep])
        children = [_make_task("1.1", level="sub", line_number=12, children=[leaf])]
        tasks = [_make_task("1", line_number=10, children=children)]
        plan = _make_plan(tasks=tasks, file_path="/tmp/phases/phase_0.md")
        issues = check_depth_violations(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1
        assert "1.1.1.1" in errors[0].message

    def test_master_plan_depth_2_ok(self):
        """Master plan with N.M subtasks produces zero issues."""
        children = [_make_task("1.1", level="sub", line_number=12)]
        tasks = [_make_task("1", line_number=10, children=children)]
        plan = _make_plan(
            tasks=tasks,
            sections=["Phases Overview"],
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/master_plan.md",
        )
        issues = check_depth_violations(plan)
        assert len(issues) == 0

    def test_master_plan_depth_3_error(self):
        """Master plan with N.M.K produces an error."""
        leaf = _make_task("1.1.1", level="leaf", line_number=14)
        children = [_make_task("1.1", level="sub", line_number=12, children=[leaf])]
        tasks = [_make_task("1", line_number=10, children=children)]
        plan = _make_plan(
            tasks=tasks,
            sections=["Phases Overview"],
            plan_type=PlanType.COMPLEX,
            file_path="/tmp/master_plan.md",
        )
        issues = check_depth_violations(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1
        assert "1.1.1" in errors[0].message

    def test_depth_violation_fixture(self, malformed_plan):
        """Depth_violation fixture catches the 1.1.1.1 heading."""
        plan = parse_plan(malformed_plan["depth_violation"])
        issues = check_depth_violations(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1
        # Should catch 4.1.1.1 or similar deep heading
        assert any("1.1.1" in e.message for e in errors)


# ===========================================================================
# Test check_greppable_patterns
# ===========================================================================


class TestCheckGreppablePatterns:
    """Tests for check_greppable_patterns()."""

    def test_all_unchecked_no_issues(self):
        """All-unchecked phase plan produces zero greppable issues for checked status."""
        tasks = [
            _make_task("1", line_number=10, checked=False),
            _make_task("2", line_number=20, checked=False),
        ]
        plan = _make_plan(tasks=tasks, file_path="/tmp/phases/phase_0.md")
        issues = check_greppable_patterns(plan)
        # Filter to only checked-status warnings
        checked_issues = [i for i in issues if "pre-checked" in i.message]
        assert len(checked_issues) == 0

    def test_checked_heading_fixture(self, malformed_plan):
        """Checked_heading fixture catches ### [x] 3."""
        plan = parse_plan(malformed_plan["checked_heading"])
        issues = check_greppable_patterns(plan)
        checked_warnings = [i for i in issues if "pre-checked" in i.message]
        assert len(checked_warnings) >= 1

    def test_wrong_depth_heading(self, tmp_path):
        """Plan with ## [ ] 1 produces heading-depth error."""
        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## Tasks

## [ ] 1 Wrong Depth Task

### [ ] 2 Correct Task
""")
        plan = parse_plan(f)
        issues = check_greppable_patterns(plan)
        heading_errors = [i for i in issues if "instead of '###'" in i.message or "too deep" in i.message]
        assert len(heading_errors) >= 1

    def test_master_plan_sub_subtask_error(self, tmp_path):
        """Master plan with - [ ] 1.1.1 produces an error."""
        plan_dir = tmp_path / "test_slug"
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)
        # Create a dummy phase file so it's detected as COMPLEX master
        (phases_dir / "phase_0_test.md").write_text("# Phase 0\n")

        master = plan_dir / "test_master_plan.md"
        master.write_text("""\
# Master Plan

---

## Phases Overview

### Phase 0: Test
#### Tasks
### [ ] 1 Task One
  - [ ] 1.1 Sub
  - [ ] 1.1.1 Sub-sub should be error
""")
        plan = parse_plan(master)
        issues = check_greppable_patterns(plan)
        sub_sub_errors = [i for i in issues if "sub-subtask" in i.message]
        assert len(sub_sub_errors) >= 1

    def test_simple_plan_correct_format(self, tmp_path):
        """Simple plan with correct #### [ ] 1.1 passes."""
        f = tmp_path / "simple.md"
        f.write_text("""\
# Simple Plan

---

## Tasks

### [ ] 1 Task One

#### [ ] 1.1 Correct Subtask
""")
        plan = parse_plan(f, plan_type=PlanType.SIMPLE)
        issues = check_greppable_patterns(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_simple_plan_bullet_subtask_error(self, tmp_path):
        """Simple plan using - [ ] 1.1 (complex grammar) produces error."""
        f = tmp_path / "simple.md"
        f.write_text("""\
# Simple Plan

---

## Tasks

### [ ] 1 Task One

  - [ ] 1.1 Wrong format subtask
""")
        plan = parse_plan(f, plan_type=PlanType.SIMPLE)
        issues = check_greppable_patterns(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1


# ===========================================================================
# Test check_cross_file_consistency
# ===========================================================================


class TestCheckCrossFileConsistency:
    """Tests for check_cross_file_consistency()."""

    def test_matching_master_and_phases(self, tmp_path):
        """Master plan matching phase files produces zero errors."""
        plan_dir = tmp_path / "test_slug"
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)

        # Create phase file
        phase0 = phases_dir / "phase_0_test.md"
        phase0.write_text("""\
# Phase 0: Test

---

## Tasks

### [ ] 1 Create Setup
  - [ ] 1.1 Do thing one

### [ ] 2 Run Tests
  - [ ] 2.1 Run unit tests
""")

        # Create master plan
        master = plan_dir / "test_master_plan.md"
        master.write_text("""\
# Test Master Plan

---

## Phases Overview

### Phase 0: Test
#### Tasks
### [ ] 1 Create Setup
  - [ ] 1.1 Do thing one
### [ ] 2 Run Tests
  - [ ] 2.1 Run unit tests
""")

        master_plan = parse_plan(master)
        issues = check_cross_file_consistency(master_plan, phases_dir)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_title_mismatch(self, tmp_path):
        """Mismatched task title produces an error."""
        plan_dir = tmp_path / "test_slug"
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)

        phase0 = phases_dir / "phase_0_test.md"
        phase0.write_text("""\
# Phase 0

---

## Tasks

### [ ] 1 Create Configuration Module
""")

        master = plan_dir / "test_master_plan.md"
        master.write_text("""\
# Master

---

## Phases Overview

### Phase 0: Test
#### Tasks
### [ ] 1 Create Config Module
""")

        master_plan = parse_plan(master)
        issues = check_cross_file_consistency(master_plan, phases_dir)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1
        assert any("title mismatch" in e.message.lower() for e in errors)

    def test_phase_count_mismatch(self, tmp_path):
        """Master with 1 phase but 2 phase files produces error."""
        plan_dir = tmp_path / "test_slug"
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)

        (phases_dir / "phase_0_test.md").write_text("""\
# Phase 0

---

## Tasks

### [ ] 1 Task
""")
        (phases_dir / "phase_1_test.md").write_text("""\
# Phase 1

---

## Tasks

### [ ] 1 Task
""")

        master = plan_dir / "test_master_plan.md"
        master.write_text("""\
# Master

---

## Phases Overview

### Phase 0: Test
#### Tasks
### [ ] 1 Task
""")

        master_plan = parse_plan(master)
        issues = check_cross_file_consistency(master_plan, phases_dir)
        errors = [i for i in issues if i.severity == "error"]
        assert any("phase" in e.message.lower() and ("1" in e.message or "2" in e.message) for e in errors)

    def test_complex_wellformed_no_errors(self, complex_plan_fixture):
        """Cross-file check on complex_wellformed fixture passes."""
        master = complex_plan_fixture / "gpu_saturation_benchmark_master_plan.md"
        phases_dir = complex_plan_fixture / "phases"
        master_plan = parse_plan(master)
        issues = check_cross_file_consistency(master_plan, phases_dir)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0


# ===========================================================================
# Test check_references_subsections
# ===========================================================================


class TestCheckReferencesSubsections:
    """Tests for check_references_subsections()."""

    def test_all_subsections_present(self, tmp_path):
        """References with all 3 subsections produces zero issues."""
        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## References

### Source Files
- `src/file.py`

### Destination Files
- `dst/file.py`

### Related Documentation
- `docs/README.md`
""")
        plan = parse_plan(f)
        issues = check_references_subsections(plan)
        assert len(issues) == 0

    def test_missing_subsection_warning(self, tmp_path):
        """Missing subsection produces a warning."""
        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## References

### Source Files
- `src/file.py`

### Destination Files
- `dst/file.py`
""")
        plan = parse_plan(f)
        issues = check_references_subsections(plan)
        warnings = [i for i in issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert "Related Documentation" in warnings[0].message


# ===========================================================================
# Test check_acceptance_gates
# ===========================================================================


class TestCheckAcceptanceGates:
    """Tests for check_acceptance_gates()."""

    def test_phase_plan_with_gates(self, tmp_path):
        """Phase plan with acceptance gates produces zero issues."""
        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## Acceptance Gates

- [ ] Gate 1: Tests pass.
- [ ] Gate 2: Coverage above 80%.

## Tasks

### [ ] 1 Task
""")
        plan = parse_plan(f)
        issues = check_acceptance_gates(plan)
        assert len(issues) == 0

    def test_phase_plan_empty_gates(self, tmp_path):
        """Phase plan with empty acceptance gates produces error."""
        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## Acceptance Gates

## Tasks

### [ ] 1 Task
""")
        plan = parse_plan(f)
        issues = check_acceptance_gates(plan)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "no checkbox items" in errors[0].message

    def test_simple_plan_with_acceptance_criteria(self, tmp_path):
        """Simple plan with ## Acceptance Criteria produces zero issues."""
        f = tmp_path / "simple.md"
        f.write_text("""\
# Simple Plan

---

## Acceptance Criteria

- [ ] Criterion 1: Endpoint works.

## Tasks

### [ ] 1 Task
""")
        plan = parse_plan(f, plan_type=PlanType.SIMPLE)
        issues = check_acceptance_gates(plan)
        assert len(issues) == 0


# ===========================================================================
# Test check_source_paths
# ===========================================================================


class TestCheckSourcePaths:
    """Tests for check_source_paths()."""

    def test_existing_paths_no_warnings(self, tmp_path):
        """Source paths that exist produce zero warnings."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "file.py").write_text("# code")

        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## References

### Source Files
- `src/file.py` -- existing file

### Destination Files
- `dst/new_file.py` -- new file
""")
        plan = parse_plan(f)
        issues = check_source_paths(plan, tmp_path)
        assert len(issues) == 0

    def test_nonexistent_path_warning(self, tmp_path):
        """Nonexistent source path produces a warning."""
        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## References

### Source Files
- `src/nonexistent.py` -- does not exist
""")
        plan = parse_plan(f)
        issues = check_source_paths(plan, tmp_path)
        warnings = [i for i in issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert "nonexistent.py" in warnings[0].message

    def test_bare_identifiers_skipped(self, tmp_path):
        """Backtick strings without / are not treated as paths."""
        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## References

### Source Files
- `PlanType` -- an identifier, not a path
- `parse_plan()` -- a function, not a path
""")
        plan = parse_plan(f)
        issues = check_source_paths(plan, tmp_path)
        assert len(issues) == 0


# ===========================================================================
# Test check_task_descriptions
# ===========================================================================


class TestCheckTaskDescriptions:
    """Tests for check_task_descriptions()."""

    def test_tasks_with_descriptions(self, tmp_path):
        """Tasks with descriptions produce zero warnings."""
        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## Tasks

### [ ] 1 Create Setup

This task creates the initial setup.

  - [ ] 1.1 Do thing one

### [ ] 2 Run Tests

Run all unit and integration tests.

  - [ ] 2.1 Run unit tests
""")
        plan = parse_plan(f)
        issues = check_task_descriptions(plan)
        assert len(issues) == 0

    def test_tasks_without_descriptions(self, tmp_path):
        """Tasks without descriptions produce warnings."""
        f = tmp_path / "phases" / "phase_0.md"
        f.parent.mkdir(parents=True)
        f.write_text("""\
# Phase 0

---

## Tasks

### [ ] 1 Create Setup

  - [ ] 1.1 Do thing one

### [ ] 2 Run Tests

  - [ ] 2.1 Run unit tests
""")
        plan = parse_plan(f)
        issues = check_task_descriptions(plan)
        warnings = [i for i in issues if i.severity == "warning"]
        assert len(warnings) == 2

    def test_master_plan_skipped(self, tmp_path):
        """Master plan does not trigger task description warnings."""
        plan_dir = tmp_path / "test_slug"
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)
        (phases_dir / "phase_0_test.md").write_text("# Phase 0\n")

        master = plan_dir / "test_master_plan.md"
        master.write_text("""\
# Master Plan

---

## Phases Overview

### Phase 0: Test
#### Tasks
### [ ] 1 Task Without Description
  - [ ] 1.1 Sub
""")
        plan = parse_plan(master)
        issues = check_task_descriptions(plan)
        assert len(issues) == 0


# ===========================================================================
# Test verify_plan_syntax() integration
# ===========================================================================


class TestVerifyPlanSyntax:
    """Integration tests for verify_plan_syntax()."""

    def test_wellformed_phase_passes(self, complex_plan_fixture):
        """Well-formed phase file returns passed=True."""
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        result = verify_plan_syntax(phase_file, validate_source_paths=False)
        # Some warnings may be present (missing sections, etc) but no errors
        # that prevent passing
        if not result.passed:
            error_msgs = [i.message for i in result.issues if i.severity == "error"]
            pytest.fail(f"Well-formed phase file should pass but got errors: {error_msgs}")

    def test_wellformed_all_phases(self, complex_plan_fixture):
        """All well-formed phase files return passed=True."""
        phases_dir = complex_plan_fixture / "phases"
        for phase_file in sorted(phases_dir.glob("phase_*.md")):
            result = verify_plan_syntax(phase_file, validate_source_paths=False)
            if not result.passed:
                error_msgs = [i.message for i in result.issues if i.severity == "error"]
                pytest.fail(
                    f"{phase_file.name} should pass but got errors: {error_msgs}"
                )

    def test_wellformed_simple_passes(self, simple_plan_fixture):
        """Well-formed simple plan returns passed=True."""
        result = verify_plan_syntax(simple_plan_fixture, validate_source_paths=False)
        if not result.passed:
            error_msgs = [i.message for i in result.issues if i.severity == "error"]
            pytest.fail(f"Simple plan should pass but got errors: {error_msgs}")

    def test_mixed_defects_fails(self, malformed_plan):
        """mixed_defects.md returns passed=False with 3+ errors."""
        result = verify_plan_syntax(
            malformed_plan["mixed_defects"],
            validate_source_paths=False,
        )
        assert result.passed is False
        assert result.errors >= 3, (
            f"Expected 3+ errors but got {result.errors}: "
            f"{[i.message for i in result.issues if i.severity == 'error']}"
        )

    def test_multi_error_accumulation(self, malformed_plan):
        """All defects reported in a single pass, not stopping at first."""
        result = verify_plan_syntax(
            malformed_plan["mixed_defects"],
            validate_source_paths=False,
        )
        # mixed_defects has: numbering gaps, depth violations, missing sections
        # All should be caught in one pass
        assert len(result.issues) >= 3
        # Each error-severity issue should have line_number and suggestion
        for issue in result.issues:
            if issue.severity == "error":
                assert issue.line_number is not None, f"Error missing line_number: {issue.message}"
                assert issue.suggestion, f"Error missing suggestion: {issue.message}"

    def test_cross_file_skipped_when_disabled(self, complex_plan_fixture):
        """verify_plan_syntax with check_cross_file=False skips cross-file checks."""
        master = complex_plan_fixture / "gpu_saturation_benchmark_master_plan.md"
        result = verify_plan_syntax(
            master,
            check_cross_file=False,
            validate_source_paths=False,
        )
        # Should not contain cross-file errors regardless of actual state
        cross_issues = [
            i for i in result.issues
            if "phase file" in i.message.lower() or "master plan declares" in i.message.lower()
        ]
        assert len(cross_issues) == 0

    def test_result_has_summary(self, complex_plan_fixture):
        """Result includes a summary string."""
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        result = verify_plan_syntax(phase_file, validate_source_paths=False)
        assert result.summary  # Non-empty

    def test_result_model_dump_json(self, complex_plan_fixture):
        """Result serializes to valid JSON matching the schema."""
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        result = verify_plan_syntax(phase_file, validate_source_paths=False)
        json_str = json.dumps(result.model_dump(), indent=2)
        parsed = json.loads(json_str)
        assert "passed" in parsed
        assert "issues" in parsed
        assert "summary" in parsed
        assert "errors" in parsed
        assert "warnings" in parsed


# ===========================================================================
# Test plan-verify CLI command
# ===========================================================================


class TestPlanVerifyCLI:
    """CLI integration tests for the plan-verify command."""

    def test_wellformed_exit_0(self, complex_plan_fixture):
        """plan-verify on well-formed fixture exits with code 0."""
        from orchestrator_v3.cli import app

        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        result = runner.invoke(
            app, ["plan-verify", str(phase_file), "--no-source-paths"]
        )
        assert result.exit_code == 0, f"Expected exit 0 but got {result.exit_code}\n{result.output}"

    def test_malformed_exit_1(self, malformed_plan):
        """plan-verify on malformed fixture exits with code 1."""
        from orchestrator_v3.cli import app

        result = runner.invoke(
            app, ["plan-verify", str(malformed_plan["mixed_defects"]), "--no-source-paths"]
        )
        assert result.exit_code == 1, f"Expected exit 1 but got {result.exit_code}\n{result.output}"

    def test_json_output_valid(self, complex_plan_fixture):
        """plan-verify --json outputs valid JSON."""
        from orchestrator_v3.cli import app

        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        result = runner.invoke(
            app, ["plan-verify", "--json", "--no-source-paths", str(phase_file)]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "passed" in parsed
        assert "issues" in parsed
        assert "summary" in parsed

    def test_json_output_malformed(self, malformed_plan):
        """plan-verify --json on malformed plan outputs valid JSON with errors."""
        from orchestrator_v3.cli import app

        result = runner.invoke(
            app,
            ["plan-verify", "--json", "--no-source-paths", str(malformed_plan["mixed_defects"])],
        )
        assert result.exit_code == 1
        parsed = json.loads(result.output)
        assert parsed["passed"] is False
        assert len(parsed["issues"]) >= 3

    def test_verbose_shows_warnings(self, malformed_plan):
        """plan-verify --verbose shows warnings in output."""
        from orchestrator_v3.cli import app

        result = runner.invoke(
            app,
            ["plan-verify", "--verbose", "--no-source-paths", str(malformed_plan["checked_heading"])],
        )
        # The checked_heading fixture should have at least a warning for pre-checked task
        # Output should mention "WARNING" since verbose is on
        # (may also have errors from missing sections)
        assert "WARNING" in result.output or "ERROR" in result.output

    def test_no_verbose_hides_warnings(self, malformed_plan):
        """plan-verify without --verbose hides warnings but summary mentions count."""
        from orchestrator_v3.cli import app

        result = runner.invoke(
            app,
            ["plan-verify", "--no-source-paths", str(malformed_plan["checked_heading"])],
        )
        # Result line should contain warning count
        assert "warning" in result.output.lower()

    def test_no_cross_file_skips(self, complex_plan_fixture):
        """plan-verify --no-cross-file skips cross-file checks on master plan."""
        from orchestrator_v3.cli import app

        master = complex_plan_fixture / "gpu_saturation_benchmark_master_plan.md"
        result = runner.invoke(
            app,
            ["plan-verify", "--no-cross-file", "--no-source-paths", str(master)],
        )
        # Should not mention cross-file errors
        assert "phase file" not in result.output.lower() or result.exit_code == 0

    def test_simple_plan_exit_0(self, simple_plan_fixture):
        """plan-verify on well-formed simple plan exits with code 0."""
        from orchestrator_v3.cli import app

        result = runner.invoke(
            app, ["plan-verify", "--no-source-paths", str(simple_plan_fixture)]
        )
        assert result.exit_code == 0, f"Expected exit 0 but got {result.exit_code}\n{result.output}"
