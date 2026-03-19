"""Comprehensive tests for plan_tool parser and data models."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator_v3.config import PlanType
from orchestrator_v3.plan_tool import (
    ParsedPlan,
    ParsedSection,
    ParsedTask,
    PlanParser,
    PlanVerificationIssue,
    PlanVerificationResult,
    parse_plan,
)


# ---------------------------------------------------------------------------
# Task 1.7: Model round-trip smoke tests
# ---------------------------------------------------------------------------


class TestModelRoundTrip:
    """Verify all data models serialize/deserialize cleanly."""

    def test_parsed_task_round_trip(self):
        task = ParsedTask(
            number="1.2",
            title="Implement feature",
            level="sub",
            line_number=42,
            line_range=(42, 50),
            checked=False,
            children=[
                ParsedTask(
                    number="1.2.1",
                    title="Step one",
                    level="leaf",
                    line_number=45,
                    line_range=(45, 47),
                    checked=True,
                    section="Tasks",
                )
            ],
            section="Tasks",
        )
        json_str = task.model_dump_json()
        restored = ParsedTask.model_validate_json(json_str)
        assert restored.number == task.number
        assert restored.title == task.title
        assert restored.level == task.level
        assert restored.line_number == task.line_number
        assert restored.line_range == task.line_range
        assert restored.checked == task.checked
        assert len(restored.children) == 1
        assert restored.children[0].number == "1.2.1"
        assert restored.section == task.section

    def test_parsed_section_round_trip(self):
        section = ParsedSection(
            name="Tasks",
            line_number=10,
            line_range=(10, 50),
            tasks=[
                ParsedTask(
                    number="1",
                    title="First task",
                    level="top",
                    line_number=12,
                    line_range=(12, 20),
                )
            ],
        )
        json_str = section.model_dump_json()
        restored = ParsedSection.model_validate_json(json_str)
        assert restored.name == section.name
        assert restored.line_range == section.line_range
        assert len(restored.tasks) == 1

    def test_parsed_plan_round_trip(self):
        plan = ParsedPlan(
            file_path="/some/plan.md",
            plan_type=PlanType.COMPLEX,
            sections=[],
            tasks=[
                ParsedTask(
                    number="1",
                    title="Task one",
                    level="top",
                    line_number=5,
                    line_range=(5, 10),
                )
            ],
            metadata={"status": "Pending", "planned_start": "2026-03-14"},
        )
        json_str = plan.model_dump_json()
        restored = ParsedPlan.model_validate_json(json_str)
        assert restored.file_path == plan.file_path
        assert restored.plan_type == PlanType.COMPLEX
        assert len(restored.tasks) == 1
        assert restored.metadata["status"] == "Pending"

    def test_verification_issue_round_trip(self):
        issue = PlanVerificationIssue(
            severity="error",
            message="Missing task 2",
            line_number=15,
            line_range=(15, 20),
            suggestion="Add ### [ ] 2 after line 14",
        )
        json_str = issue.model_dump_json()
        restored = PlanVerificationIssue.model_validate_json(json_str)
        assert restored.severity == "error"
        assert restored.message == issue.message
        assert restored.line_number == 15
        assert restored.suggestion == issue.suggestion

    def test_verification_result_round_trip(self):
        result = PlanVerificationResult(
            passed=False,
            issues=[
                PlanVerificationIssue(severity="error", message="Bad"),
                PlanVerificationIssue(severity="warning", message="Meh"),
                PlanVerificationIssue(severity="error", message="Also bad"),
            ],
            summary="2 errors, 1 warning found",
        )
        assert result.errors == 2
        assert result.warnings == 1

        json_str = result.model_dump_json()
        restored = PlanVerificationResult.model_validate_json(json_str)
        assert restored.passed is False
        assert len(restored.issues) == 3
        assert restored.errors == 2
        assert restored.warnings == 1
        assert restored.summary == "2 errors, 1 warning found"


# ---------------------------------------------------------------------------
# Task 2.7: Section tracking tests
# ---------------------------------------------------------------------------


class TestSectionTracking:
    """Verify section detection and line ranges."""

    def test_multiple_sections(self):
        content = """\
# Title

---

## Objective

Some text here.

## Tasks

### [ ] 1 First task

## References

Some refs.
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        section_names = [s.name for s in plan.sections]
        assert "Objective" in section_names
        assert "Tasks" in section_names
        assert "References" in section_names

        # Verify line numbers
        for section in plan.sections:
            assert section.line_number > 0
            assert section.line_range[0] == section.line_number
            assert section.line_range[1] >= section.line_range[0]

    def test_section_line_ranges_no_overlap(self):
        content = """\
## Section A

Line 1
Line 2

## Section B

Line 3
Line 4

## Section C

Line 5
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.sections) == 3
        for i in range(len(plan.sections) - 1):
            assert plan.sections[i].line_range[1] < plan.sections[i + 1].line_range[0]


# ---------------------------------------------------------------------------
# Task 2.8: Code-fence skipping tests
# ---------------------------------------------------------------------------


class TestCodeFenceSkipping:
    """Verify tasks inside code fences are not parsed."""

    def test_backtick_fence(self):
        content = """\
## Tasks

### [ ] 1 Real Task

```markdown
### [ ] 99 Fake Task Inside Fence
```

### [ ] 2 Another Real Task
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        numbers = [t.number for t in plan.tasks]
        assert "1" in numbers
        assert "2" in numbers
        assert "99" not in numbers

    def test_tilde_fence(self):
        content = """\
## Tasks

### [ ] 1 Real Task

~~~
### [ ] 88 Fake Task Inside Tilde Fence
~~~

### [ ] 2 Another Real Task
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        numbers = [t.number for t in plan.tasks]
        assert "1" in numbers
        assert "2" in numbers
        assert "88" not in numbers

    def test_fence_with_language(self):
        content = """\
## Tasks

### [ ] 1 Real Task

```python
### [ ] 77 Fake Task
```
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.tasks) == 1
        assert plan.tasks[0].number == "1"


# ---------------------------------------------------------------------------
# Task 2.9: Mutable-section filter tests
# ---------------------------------------------------------------------------


class TestMutableSectionFilter:
    """Verify instructional checkboxes in non-mutable sections are skipped."""

    def test_reviewer_checklist_skipped(self):
        content = """\
## Tasks

### [ ] 1 Real Task

## Reviewer Checklist

- [ ] Check formatting
- [ ] Verify numbering
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.tasks) == 1
        assert plan.tasks[0].number == "1"

    def test_acceptance_gates_skipped(self):
        content = """\
## Acceptance Gates

- [ ] Gate 1: All tests pass.
- [ ] Gate 2: Coverage above 80%.

## Tasks

### [ ] 1 Implement feature
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.tasks) == 1
        assert plan.tasks[0].title == "Implement feature"

    def test_global_acceptance_gates_skipped(self):
        content = """\
## Global Acceptance Gates

- [ ] Gate 1: End-to-end test passes.

## Tasks

### [ ] 1 Task in Tasks section
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.tasks) == 1

    def test_dependency_gates_skipped(self):
        content = """\
## Dependency Gates

- [ ] Dep 1: Phase 0 complete

## Tasks

### [ ] 1 Real Task
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.tasks) == 1

    def test_example_section_skipped(self):
        content = """\
## Example Output

### [ ] 1 This Is An Example Task

## Tasks

### [ ] 1 Actual Task
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.tasks) == 1
        assert plan.tasks[0].section == "Tasks"

    def test_template_section_skipped(self):
        content = """\
## Template Reference

### [ ] 1 Template Task

## Tasks

### [ ] 1 Real Task
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.tasks) == 1
        assert plan.tasks[0].section == "Tasks"

    def test_acceptance_criteria_skipped(self):
        content = """\
## Acceptance Criteria

- [ ] The system meets all requirements.

## Tasks

### [ ] 1 Implement
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.tasks) == 1

    def test_combined_non_mutable_sections(self):
        """All non-mutable sections together produce only tasks from Tasks."""
        content = """\
## Reviewer Checklist

- [ ] Check this

## Global Acceptance Gates

- [ ] Gate 1

## Dependency Gates

- [ ] Dep 1

## Tasks

### [ ] 1 Real Task
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert len(plan.tasks) == 1
        assert plan.tasks[0].title == "Real Task"


# ---------------------------------------------------------------------------
# Task 3.5: Complex plan fixture parsing tests
# ---------------------------------------------------------------------------


class TestComplexPlanParsing:
    """Parse complex plan phase files and verify structure."""

    def test_phase_0_task_count(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)

        assert plan.plan_type == PlanType.COMPLEX
        assert len(plan.tasks) == 7

    def test_phase_0_task_numbers(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)

        numbers = [t.number for t in plan.tasks]
        assert numbers == ["1", "2", "3", "4", "5", "6", "7"]

    def test_phase_0_task_titles(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)

        assert plan.tasks[0].title == "Create Package Structure and Config Manager"
        assert plan.tasks[1].title == "Implement GPU and CPU Monitoring"
        assert plan.tasks[6].title == "Integration Test the Framework"

    def test_phase_0_nesting(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)

        # Task 1 has children 1.1 and 1.2
        assert len(plan.tasks[0].children) == 2
        assert plan.tasks[0].children[0].number == "1.1"
        assert plan.tasks[0].children[1].number == "1.2"

        # Task 3 has children 3.1 and 3.2
        assert len(plan.tasks[2].children) == 2

        # Task 7 has 4 children
        assert len(plan.tasks[6].children) == 4

    def test_phase_0_subtask_count(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)

        total_subtasks = sum(len(t.children) for t in plan.tasks)
        # 1.1,1.2, 2.1, 3.1,3.2, 4.1, 5.1, 6.1,6.2, 7.1,7.2,7.3,7.4 = 13
        assert total_subtasks == 13

    def test_phase_0_all_unchecked(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)

        for task in plan.tasks:
            assert task.checked is False
            for child in task.children:
                assert child.checked is False

    def test_phase_0_no_acceptance_gates_in_tasks(self, complex_plan_fixture):
        """Acceptance Gates checkboxes must NOT appear as tasks."""
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)

        all_titles = []
        for task in plan.tasks:
            all_titles.append(task.title)
            for child in task.children:
                all_titles.append(child.title)

        for title in all_titles:
            assert not title.startswith("Gate ")

    def test_phase_1_task_count(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_1_instructor_xl_sweep.md"
        plan = parse_plan(phase_file)

        assert len(plan.tasks) == 6

    def test_phase_1_subtask_counts(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_1_instructor_xl_sweep.md"
        plan = parse_plan(phase_file)

        expected_children = [5, 2, 2, 3, 5, 5]
        for task, expected in zip(plan.tasks, expected_children):
            assert len(task.children) == expected, (
                f"Task {task.number} expected {expected} children, got {len(task.children)}"
            )


# ---------------------------------------------------------------------------
# Task 3.6: Mixed checked/unchecked tests
# ---------------------------------------------------------------------------


class TestCheckedStatus:
    """Verify checked detection for all checkbox styles."""

    def test_unchecked(self):
        content = """\
## Tasks

### [ ] 1 Unchecked Task
"""
        plan = PlanParser(content, plan_type=PlanType.COMPLEX).parse()
        assert plan.tasks[0].checked is False

    def test_checked_x(self):
        content = """\
## Tasks

### [x] 1 Checked with x
"""
        plan = PlanParser(content, plan_type=PlanType.COMPLEX).parse()
        assert plan.tasks[0].checked is True

    def test_checked_checkmark(self):
        content = """\
## Tasks

### [\u2705] 1 Checked with checkmark
"""
        plan = PlanParser(content, plan_type=PlanType.COMPLEX).parse()
        assert plan.tasks[0].checked is True

    def test_mixed_checked_unchecked(self):
        content = """\
## Tasks

### [ ] 1 First
### [\u2705] 2 Second
### [x] 3 Third
"""
        plan = PlanParser(content, plan_type=PlanType.COMPLEX).parse()
        assert plan.tasks[0].checked is False
        assert plan.tasks[1].checked is True
        assert plan.tasks[2].checked is True


# ---------------------------------------------------------------------------
# Task 3.7: Master plan Phases Overview parsing
# ---------------------------------------------------------------------------


class TestMasterPlanParsing:
    """Verify parser handles master plan's Phases Overview section."""

    def test_master_plan_phases_overview(self, complex_plan_fixture):
        master_file = complex_plan_fixture / "gpu_saturation_benchmark_master_plan.md"
        plan = parse_plan(master_file)

        assert plan.plan_type == PlanType.COMPLEX

        # The master plan has tasks from all 4 phases in Phases Overview
        # Phase 0: 7, Phase 1: 6, Phase 2: 4, Phase 3: 2 = 19 total top-level
        assert len(plan.tasks) == 19

    def test_master_plan_global_gates_skipped(self, complex_plan_fixture):
        master_file = complex_plan_fixture / "gpu_saturation_benchmark_master_plan.md"
        plan = parse_plan(master_file)

        # Global Acceptance Gates checkboxes should not be in tasks
        all_titles = [t.title for t in plan.tasks]
        for title in all_titles:
            assert not title.startswith("Gate ")


# ---------------------------------------------------------------------------
# Task 4.4: Simple plan fixture parsing
# ---------------------------------------------------------------------------


class TestSimplePlanParsing:
    """Parse simple plan fixture and verify structure."""

    def test_simple_plan_type(self, simple_plan_fixture):
        plan = parse_plan(simple_plan_fixture)
        assert plan.plan_type == PlanType.SIMPLE

    def test_simple_top_task_count(self, simple_plan_fixture):
        plan = parse_plan(simple_plan_fixture)
        assert len(plan.tasks) == 3

    def test_simple_task_numbers(self, simple_plan_fixture):
        plan = parse_plan(simple_plan_fixture)
        numbers = [t.number for t in plan.tasks]
        assert numbers == ["1", "2", "3"]

    def test_simple_task_titles(self, simple_plan_fixture):
        plan = parse_plan(simple_plan_fixture)
        assert plan.tasks[0].title == "Implement HealthChecker Utility"
        assert plan.tasks[1].title == "Add /healthz Route"
        assert plan.tasks[2].title == "Write Tests"

    def test_simple_subtask_counts(self, simple_plan_fixture):
        plan = parse_plan(simple_plan_fixture)
        # Task 1: #### 1.1 -> 1 subtask
        # Task 2: #### 2.1, #### 2.2 -> 2 subtasks
        # Task 3: #### 3.1, #### 3.2 -> 2 subtasks
        assert len(plan.tasks[0].children) == 1
        assert len(plan.tasks[1].children) == 2
        assert len(plan.tasks[2].children) == 2

    def test_simple_leaf_step_counts(self, simple_plan_fixture):
        plan = parse_plan(simple_plan_fixture)
        # Task 1 -> 1.1 -> 3 leaf steps (1.1.1, 1.1.2, 1.1.3)
        assert len(plan.tasks[0].children[0].children) == 3

        # Task 3 -> 3.1 -> 3 leaf steps (3.1.1, 3.1.2, 3.1.3)
        assert len(plan.tasks[2].children[0].children) == 3

        # Task 3 -> 3.2 -> 2 leaf steps (3.2.1, 3.2.2)
        assert len(plan.tasks[2].children[1].children) == 2

    def test_simple_no_reviewer_checklist_tasks(self, simple_plan_fixture):
        """Reviewer Checklist checkboxes must not appear as tasks."""
        plan = parse_plan(simple_plan_fixture)

        def _collect_all_numbers(tasks):
            result = []
            for t in tasks:
                result.append(t.number)
                result.extend(_collect_all_numbers(t.children))
            return result

        all_numbers = _collect_all_numbers(plan.tasks)
        # If reviewer checklist leaked, we'd see unexpected numbers
        for num in all_numbers:
            parts = num.split(".")
            assert all(p.isdigit() for p in parts)

    def test_simple_no_acceptance_criteria_tasks(self, simple_plan_fixture):
        """Acceptance Criteria checkboxes must not appear as tasks."""
        plan = parse_plan(simple_plan_fixture)

        all_titles = []
        for t in plan.tasks:
            all_titles.append(t.title)
            for child in t.children:
                all_titles.append(child.title)
                for leaf in child.children:
                    all_titles.append(leaf.title)

        for title in all_titles:
            assert "GET /healthz" not in title


# ---------------------------------------------------------------------------
# Task 4.5: Three-level nesting tests
# ---------------------------------------------------------------------------


class TestThreeLevelNesting:
    """Verify leaf steps nest correctly under subtasks in simple plans."""

    def test_leaf_nests_under_correct_subtask(self):
        content = """\
## Tasks

### [ ] 1 Top Task

#### [ ] 1.1 First Sub

  - [ ] 1.1.1 Step A
  - [ ] 1.1.2 Step B

#### [ ] 1.2 Second Sub

  - [ ] 1.2.1 Step C
"""
        plan = PlanParser(content, plan_type=PlanType.SIMPLE).parse()

        assert len(plan.tasks) == 1
        top = plan.tasks[0]
        assert len(top.children) == 2

        sub_1_1 = top.children[0]
        assert sub_1_1.number == "1.1"
        assert len(sub_1_1.children) == 2
        assert sub_1_1.children[0].number == "1.1.1"
        assert sub_1_1.children[1].number == "1.1.2"

        sub_1_2 = top.children[1]
        assert sub_1_2.number == "1.2"
        assert len(sub_1_2.children) == 1
        assert sub_1_2.children[0].number == "1.2.1"

    def test_levels_are_correct(self):
        content = """\
## Tasks

### [ ] 1 Top

#### [ ] 1.1 Sub

  - [ ] 1.1.1 Leaf
"""
        plan = PlanParser(content, plan_type=PlanType.SIMPLE).parse()

        assert plan.tasks[0].level == "top"
        assert plan.tasks[0].children[0].level == "sub"
        assert plan.tasks[0].children[0].children[0].level == "leaf"


# ---------------------------------------------------------------------------
# Task 5.5: Integration test with complex_wellformed fixture
# ---------------------------------------------------------------------------


class TestComplexIntegration:
    """Full integration tests with complex_wellformed fixture."""

    def test_parse_plan_phase_0(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)

        assert plan.plan_type == PlanType.COMPLEX
        assert plan.file_path == str(phase_file)
        assert len(plan.tasks) == 7

        # Metadata
        assert plan.metadata.get("status") == "Pending"
        assert plan.metadata.get("planned_start") == "2026-02-11"
        assert plan.metadata.get("target_end") == "2026-02-12"

        # Sections present
        section_names = [s.name for s in plan.sections]
        assert "Tasks" in section_names
        assert "Acceptance Gates" in section_names

    def test_parse_plan_all_phases(self, complex_plan_fixture):
        """Parse all 4 phase files without error."""
        phases_dir = complex_plan_fixture / "phases"
        phase_files = sorted(phases_dir.glob("phase_*.md"))
        assert len(phase_files) == 4

        expected_top_counts = [7, 6, 4, 2]
        for phase_file, expected_count in zip(phase_files, expected_top_counts):
            plan = parse_plan(phase_file)
            assert plan.plan_type == PlanType.COMPLEX
            assert len(plan.tasks) == expected_count, (
                f"{phase_file.name}: expected {expected_count} top tasks, got {len(plan.tasks)}"
            )

    def test_line_numbers_accurate(self, complex_plan_fixture):
        """Verify line numbers match the actual lines in the file."""
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        content = phase_file.read_text()
        lines = content.splitlines()
        plan = parse_plan(phase_file)

        for task in plan.tasks:
            # Line numbers are 1-indexed
            actual_line = lines[task.line_number - 1]
            assert f"### [" in actual_line
            assert task.number in actual_line

            for child in task.children:
                actual_child_line = lines[child.line_number - 1]
                assert f"- [" in actual_child_line
                assert child.number in actual_child_line


# ---------------------------------------------------------------------------
# Task 5.6: Integration test with simple_wellformed fixture
# ---------------------------------------------------------------------------


class TestSimpleIntegration:
    """Full integration test with simple_wellformed fixture."""

    def test_parse_plan_simple(self, simple_plan_fixture):
        plan = parse_plan(simple_plan_fixture)

        assert plan.plan_type == PlanType.SIMPLE
        assert plan.file_path == str(simple_plan_fixture)
        assert len(plan.tasks) == 3

        # Verify three-level hierarchy
        # Task 1 -> 1.1 -> 1.1.1, 1.1.2, 1.1.3
        task1 = plan.tasks[0]
        assert task1.number == "1"
        assert len(task1.children) == 1
        assert len(task1.children[0].children) == 3

    def test_simple_line_numbers_accurate(self, simple_plan_fixture):
        """Verify line numbers match actual lines."""
        content = simple_plan_fixture.read_text()
        lines = content.splitlines()
        plan = parse_plan(simple_plan_fixture)

        for task in plan.tasks:
            actual_line = lines[task.line_number - 1]
            assert "### [" in actual_line
            assert task.number in actual_line

            for child in task.children:
                actual_line = lines[child.line_number - 1]
                assert "#### [" in actual_line or "- [" in actual_line
                assert child.number in actual_line


# ---------------------------------------------------------------------------
# Task 5.7: Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty files, headers only, tasks without sections."""

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.md"
        empty.write_text("")
        plan = parse_plan(empty)

        assert len(plan.tasks) == 0
        assert len(plan.sections) == 0
        assert plan.metadata == {}

    def test_headers_only_no_tasks(self, tmp_path):
        f = tmp_path / "headers_only.md"
        f.write_text("""\
# My Plan

## Objective

Some text.

## Scope

More text.
""")
        plan = parse_plan(f)

        assert len(plan.tasks) == 0
        assert len(plan.sections) >= 2

    def test_tasks_without_section_headings(self, tmp_path):
        """Tasks not under any ## section should still be extracted."""
        f = tmp_path / "no_sections.md"
        f.write_text("""\
# Plan

### [ ] 1 Task without section
### [ ] 2 Another task
""")
        plan = parse_plan(f, plan_type=PlanType.COMPLEX)

        assert len(plan.tasks) == 2
        assert plan.tasks[0].number == "1"
        assert plan.tasks[1].number == "2"
        # Section should be empty string since no ## section is active
        assert plan.tasks[0].section == ""

    def test_file_with_only_metadata(self, tmp_path):
        f = tmp_path / "metadata_only.md"
        f.write_text("""\
# My Plan

**Status:** Pending
**Author:** Alice

---
""")
        plan = parse_plan(f)

        assert plan.metadata.get("status") == "Pending"
        assert plan.metadata.get("author") == "Alice"
        assert len(plan.tasks) == 0


# ---------------------------------------------------------------------------
# Task 6.1-6.5: Validation against real corpus plans
# ---------------------------------------------------------------------------


class TestCorpusValidation:
    """Validate parser against the full complex_wellformed corpus."""

    def test_phase_files_no_exceptions(self, complex_plan_fixture):
        """Every phase file parses without exceptions."""
        phases_dir = complex_plan_fixture / "phases"
        for phase_file in sorted(phases_dir.glob("phase_*.md")):
            plan = parse_plan(phase_file)
            assert plan.plan_type == PlanType.COMPLEX
            assert len(plan.tasks) > 0

    def test_master_plan_no_exceptions(self, complex_plan_fixture):
        """Master plan parses without exceptions."""
        master = complex_plan_fixture / "gpu_saturation_benchmark_master_plan.md"
        plan = parse_plan(master)
        assert plan.plan_type == PlanType.COMPLEX

    def test_no_false_positives_from_acceptance_gates(self, complex_plan_fixture):
        """No tasks should come from Acceptance Gates sections across all files."""
        phases_dir = complex_plan_fixture / "phases"
        for phase_file in sorted(phases_dir.glob("phase_*.md")):
            plan = parse_plan(phase_file)
            for task in plan.tasks:
                assert not task.title.startswith("Gate "), (
                    f"False positive from Acceptance Gates in {phase_file.name}: {task.title}"
                )

    def test_no_false_positives_from_code_fences(self, complex_plan_fixture):
        """No tasks should come from code fences across all files."""
        phases_dir = complex_plan_fixture / "phases"
        for phase_file in sorted(phases_dir.glob("phase_*.md")):
            content = phase_file.read_text()
            plan = parse_plan(phase_file)
            # If fences contain ### patterns, they should not appear as tasks
            # Verify task numbers are sequential starting from 1
            for i, task in enumerate(plan.tasks):
                assert task.number == str(i + 1), (
                    f"Non-sequential task number in {phase_file.name}: {task.number}"
                )

    def test_line_numbers_all_phases(self, complex_plan_fixture):
        """Verify line number accuracy across all phase files."""
        phases_dir = complex_plan_fixture / "phases"
        for phase_file in sorted(phases_dir.glob("phase_*.md")):
            content = phase_file.read_text()
            lines = content.splitlines()
            plan = parse_plan(phase_file)

            for task in plan.tasks:
                actual = lines[task.line_number - 1]
                assert f"### [" in actual, (
                    f"{phase_file.name} task {task.number}: "
                    f"line {task.line_number} = {actual!r}"
                )

                for child in task.children:
                    actual = lines[child.line_number - 1]
                    assert f"- [" in actual, (
                        f"{phase_file.name} subtask {child.number}: "
                        f"line {child.line_number} = {actual!r}"
                    )

    def test_simple_wellformed_no_false_positives(self, simple_plan_fixture):
        """Simple plan has no false positives from Reviewer Checklist or Acceptance Criteria."""
        plan = parse_plan(simple_plan_fixture)

        def _count_all(tasks):
            total = len(tasks)
            for t in tasks:
                total += _count_all(t.children)
            return total

        # Expected: 3 top + 5 sub + 8 leaf = 16 total
        total = _count_all(plan.tasks)
        assert total == 16


# ---------------------------------------------------------------------------
# Additional: Plan type detection
# ---------------------------------------------------------------------------


class TestPlanTypeDetection:
    """Verify auto-detection of plan type."""

    def test_phases_dir_parent_detected_as_complex(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)
        assert plan.plan_type == PlanType.COMPLEX

    def test_sibling_phases_dir_detected_as_complex(self, complex_plan_fixture):
        master = complex_plan_fixture / "gpu_saturation_benchmark_master_plan.md"
        plan = parse_plan(master)
        assert plan.plan_type == PlanType.COMPLEX

    def test_no_phases_dir_detected_as_simple(self, simple_plan_fixture):
        plan = parse_plan(simple_plan_fixture)
        assert plan.plan_type == PlanType.SIMPLE

    def test_explicit_plan_type_overrides_detection(self, simple_plan_fixture):
        """Explicit plan_type overrides auto-detection."""
        plan = parse_plan(simple_plan_fixture, plan_type=PlanType.COMPLEX)
        assert plan.plan_type == PlanType.COMPLEX


# ---------------------------------------------------------------------------
# Additional: Metadata extraction
# ---------------------------------------------------------------------------


class TestMetadataExtraction:
    """Verify metadata key-value extraction from header block."""

    def test_metadata_from_phase_file(self, complex_plan_fixture):
        phase_file = complex_plan_fixture / "phases" / "phase_0_benchmark_framework.md"
        plan = parse_plan(phase_file)

        assert plan.metadata["status"] == "Pending"
        assert plan.metadata["planned_start"] == "2026-02-11"
        assert plan.metadata["target_end"] == "2026-02-12"
        assert "last_updated" in plan.metadata

    def test_metadata_stops_at_separator(self):
        content = """\
# Title

**Status:** Active
**Author:** Bob

---

**ShouldNotAppear:** True

## Tasks

### [ ] 1 Task
"""
        parser = PlanParser(content, plan_type=PlanType.COMPLEX)
        plan = parser.parse()

        assert plan.metadata["status"] == "Active"
        assert plan.metadata["author"] == "Bob"
        assert "shouldnotappear" not in plan.metadata

    def test_no_metadata_in_simple_plan(self, simple_plan_fixture):
        """Simple plan starts with # Title then --- immediately."""
        plan = parse_plan(simple_plan_fixture)
        # The simple test plan has no **Key:** lines before ---
        assert len(plan.metadata) == 0
