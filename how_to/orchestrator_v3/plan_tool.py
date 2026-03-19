"""Plan parser, data models, verification, status/query, and write operations for structured plan files.

Parses both simple plans (single file with ###/####/- [ ] three-level nesting)
and complex plans (master + phase files with ###/- [ ] two-level nesting).
Tracks sections, skips code fences, and filters out instructional checkboxes.

Verification functions check structural correctness, numbering, depth,
required sections, cross-file consistency, and other plan constraints.

Status/query functions (``plan_status``, ``plan_show``) provide compact
progress summaries and task subtree extraction for LLM and human consumption.

Write operations (``plan_sync``, ``plan_render_master``, ``plan_reconcile``)
project orchestrator state onto plan markdown checkmarks. State is always
authoritative; plan checkmarks are a derived view maintained by deterministic
Python code, never by LLM manual editing.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from orchestrator_v3.config import Mode, OrchestratorSettings, PlanType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for task matching
# ---------------------------------------------------------------------------

# Complex plans: ### [ ] N Title  and  - [ ] N.M Subtitle  and  (4-space) - [ ] N.M.K Step
COMPLEX_TOP_RE = re.compile(r"^### \[[ x\u2705]\] (\d+)\s+(.*)")
COMPLEX_SUB_RE = re.compile(r"^\s{2}- \[[ x\u2705]\] (\d+\.\d+)\s+(.*)")
COMPLEX_LEAF_RE = re.compile(r"^\s{4}- \[[ x\u2705]\] (\d+\.\d+\.\d+)\s+(.*)")

# Simple plans: ### [ ] N Title, #### [ ] N.M Subtitle, - [ ] N.M.K Step
SIMPLE_TOP_RE = re.compile(r"^### \[[ x\u2705]\] (\d+)\s+(.*)")
SIMPLE_SUB_RE = re.compile(r"^#### \[[ x\u2705]\] (\d+\.\d+)\s+(.*)")
SIMPLE_LEAF_RE = re.compile(r"^\s{2}- \[[ x\u2705]\] (\d+\.\d+\.\d+)\s+(.*)")

# Section heading: exactly ## followed by space
SECTION_RE = re.compile(r"^## (.+)")

# Metadata key-value: **Key:** value
METADATA_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.*)")

# Code fence: ``` or ~~~ with optional language identifier
CODE_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")

# Sections whose checkboxes are NOT mutable tasks
NON_MUTABLE_SECTIONS = frozenset({
    "Reviewer Checklist",
    "Acceptance Gates",
    "Acceptance Criteria",
    "Global Acceptance Gates",
    "Dependency Gates",
    "LLM Navigation & Grep Guide",
})


def _is_non_mutable_section(name: str) -> bool:
    """Return True if section checkboxes should be skipped."""
    if name in NON_MUTABLE_SECTIONS:
        return True
    if "Example" in name or "Template" in name:
        return True
    return False


_CHECKBOX_RE = re.compile(r"\[([ x\u2705])\]")


def _is_checked(line: str) -> bool:
    """Determine checked status from the checkbox bracket content."""
    m = _CHECKBOX_RE.search(line)
    if m is None:
        return False
    char = m.group(1)
    return char == "x" or char == "\u2705"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ParsedTask(BaseModel):
    """A single task extracted from a plan file."""

    model_config = ConfigDict(frozen=False)

    number: str
    title: str
    level: Literal["top", "sub", "leaf"]
    line_number: int
    line_range: tuple[int, int] = (0, 0)
    checked: bool = False
    children: list[ParsedTask] = Field(default_factory=list)
    section: str = ""


class ParsedSection(BaseModel):
    """A ## section within a plan file."""

    model_config = ConfigDict(frozen=False)

    name: str
    line_number: int
    line_range: tuple[int, int] = (0, 0)
    tasks: list[ParsedTask] = Field(default_factory=list)


class ParsedPlan(BaseModel):
    """Complete parse result for a plan file."""

    model_config = ConfigDict(frozen=False)

    file_path: str = ""
    plan_type: PlanType = PlanType.SIMPLE
    sections: list[ParsedSection] = Field(default_factory=list)
    tasks: list[ParsedTask] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class PlanVerificationIssue(BaseModel):
    """A single verification issue found in a plan."""

    severity: Literal["error", "warning"]
    message: str
    line_number: int | None = None
    line_range: tuple[int, int] | None = None
    suggestion: str | None = None


class PlanVerificationResult(BaseModel):
    """Aggregated verification result."""

    passed: bool
    issues: list[PlanVerificationIssue] = Field(default_factory=list)
    summary: str = ""

    @computed_field
    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @computed_field
    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


# ---------------------------------------------------------------------------
# Write-operation data models
# ---------------------------------------------------------------------------


class SyncResult(BaseModel):
    """Result of a plan sync or render operation."""

    model_config = ConfigDict(frozen=False)

    files_updated: int = 0
    checkmarks_toggled: int = 0
    dry_run: bool = False
    details: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary for CLI display."""
        prefix = "[DRY RUN] " if self.dry_run else ""
        return (
            f"{prefix}{self.files_updated} file(s) updated, "
            f"{self.checkmarks_toggled} checkmark(s) toggled"
        )


class DriftReport(BaseModel):
    """Result of a plan reconciliation (drift detection)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False)

    in_sync: bool = True
    state_completed: frozenset[tuple[int, int]] = frozenset()
    plan_completed: frozenset[tuple[int, int]] = frozenset()
    missing_in_plan: frozenset[tuple[int, int]] = frozenset()
    missing_in_state: frozenset[tuple[int, int]] = frozenset()

    def summary(self) -> str:
        """Human-readable summary for CLI display."""
        if self.in_sync:
            return "In sync: state and plan agree."
        parts: list[str] = []
        if self.missing_in_plan:
            items = ", ".join(f"(p{p}, t{t})" for p, t in sorted(self.missing_in_plan))
            parts.append(f"Approved in state but unchecked in plan: {items}")
        if self.missing_in_state:
            items = ", ".join(f"(p{p}, t{t})" for p, t in sorted(self.missing_in_state))
            parts.append(f"Checked in plan but not approved in state: {items}")
        return "DRIFT DETECTED:\n" + "\n".join(parts)


# ---------------------------------------------------------------------------
# PlanParser
# ---------------------------------------------------------------------------


class PlanParser:
    """Line-by-line parser for structured plan files.

    Supports two grammar branches:
      - COMPLEX: ``### [ ] N`` top-level + ``  - [ ] N.M`` subtasks
      - SIMPLE:  ``### [ ] N`` top-level + ``#### [ ] N.M`` subtasks
                 + ``  - [ ] N.M.K`` leaf steps
    """

    def __init__(
        self,
        content: str,
        file_path: str = "",
        plan_type: PlanType | None = None,
    ) -> None:
        self.content = content
        self.file_path = file_path
        self.lines = content.splitlines()
        self.plan_type = plan_type or self._detect_plan_type()

    def _detect_plan_type(self) -> PlanType:
        """Auto-detect plan type from content patterns.

        If the file path indicates a phases/ directory, it is COMPLEX.
        Otherwise, look for #### [ ] headings that indicate SIMPLE.
        """
        p = Path(self.file_path)
        if p.parent.name == "phases":
            return PlanType.COMPLEX
        if p.parent.joinpath("phases").is_dir():
            return PlanType.COMPLEX
        # Check content for #### task headings (simple plan indicator)
        for line in self.lines:
            if SIMPLE_SUB_RE.match(line):
                return PlanType.SIMPLE
        return PlanType.COMPLEX

    @staticmethod
    def _is_code_fence(line: str) -> bool:
        """Return True if the line is a code fence delimiter."""
        return CODE_FENCE_RE.match(line) is not None

    def _extract_metadata(self) -> dict[str, str]:
        """Extract **Key:** value pairs from the header block.

        The header block is the region between the first ``# Title`` line
        and the first ``---`` separator.
        """
        metadata: dict[str, str] = {}
        in_header = False
        for line in self.lines:
            if not in_header:
                if line.startswith("# "):
                    in_header = True
                continue
            if line.strip() == "---":
                break
            m = METADATA_RE.match(line)
            if m:
                key = m.group(1).strip().lower().replace(" ", "_")
                metadata[key] = m.group(2).strip()
        return metadata

    def _parse_complex_task_line(
        self, line: str, line_num: int
    ) -> ParsedTask | None:
        """Try to match a line against complex plan task patterns."""
        m = COMPLEX_TOP_RE.match(line)
        if m:
            return ParsedTask(
                number=m.group(1),
                title=m.group(2).strip(),
                level="top",
                line_number=line_num,
                checked=_is_checked(line),
            )
        m = COMPLEX_SUB_RE.match(line)
        if m:
            return ParsedTask(
                number=m.group(1),
                title=m.group(2).strip(),
                level="sub",
                line_number=line_num,
                checked=_is_checked(line),
            )
        return None

    def _parse_simple_task_line(
        self, line: str, line_num: int
    ) -> ParsedTask | None:
        """Try to match a line against simple plan task patterns.

        Order matters: check leaf (``- [ ] N.M.K``) before sub (``#### [ ] N.M``)
        before top (``### [ ] N``), because sub regex would also match on
        ``###`` lines if we used generic patterns. But since SIMPLE_SUB_RE
        requires ``####`` and SIMPLE_TOP_RE requires ``###``, order among
        headings does not matter. We check leaf first since ``- [ ]`` lines
        could match COMPLEX_SUB_RE if we are not careful.
        """
        m = SIMPLE_LEAF_RE.match(line)
        if m:
            return ParsedTask(
                number=m.group(1),
                title=m.group(2).strip(),
                level="leaf",
                line_number=line_num,
                checked=_is_checked(line),
            )
        m = SIMPLE_SUB_RE.match(line)
        if m:
            return ParsedTask(
                number=m.group(1),
                title=m.group(2).strip(),
                level="sub",
                line_number=line_num,
                checked=_is_checked(line),
            )
        m = SIMPLE_TOP_RE.match(line)
        if m:
            return ParsedTask(
                number=m.group(1),
                title=m.group(2).strip(),
                level="top",
                line_number=line_num,
                checked=_is_checked(line),
            )
        return None

    def parse(self) -> ParsedPlan:
        """Run the full parse and return a ParsedPlan."""
        metadata = self._extract_metadata()
        sections: list[ParsedSection] = []
        top_tasks: list[ParsedTask] = []

        current_section: ParsedSection | None = None
        current_top: ParsedTask | None = None
        current_sub: ParsedTask | None = None
        in_fence = False
        in_non_mutable = False

        # Track all tasks with their line numbers so we can compute line_range
        all_task_entries: list[tuple[ParsedTask, int]] = []  # (task, line_num)

        for idx, line in enumerate(self.lines):
            line_num = idx + 1  # 1-indexed

            # Code fence toggle
            if self._is_code_fence(line):
                in_fence = not in_fence
                continue

            if in_fence:
                continue

            # Section tracking
            sm = SECTION_RE.match(line)
            if sm:
                section_name = sm.group(1).strip()
                # Finalize previous section's line_range
                if current_section is not None:
                    current_section.line_range = (
                        current_section.line_number,
                        line_num - 1,
                    )
                    sections.append(current_section)
                current_section = ParsedSection(
                    name=section_name,
                    line_number=line_num,
                )
                in_non_mutable = _is_non_mutable_section(section_name)
                continue

            # Skip task matching in non-mutable sections
            if in_non_mutable:
                continue

            # Task matching
            task: ParsedTask | None = None
            if self.plan_type == PlanType.COMPLEX:
                task = self._parse_complex_task_line(line, line_num)
            else:
                task = self._parse_simple_task_line(line, line_num)

            if task is None:
                continue

            # Assign section context
            if current_section is not None:
                task.section = current_section.name

            all_task_entries.append((task, line_num))

            # Parent-child linking
            if task.level == "top":
                current_top = task
                current_sub = None
                top_tasks.append(task)
                if current_section is not None:
                    current_section.tasks.append(task)
            elif task.level == "sub":
                current_sub = task
                if current_top is not None:
                    # Verify parent number matches
                    parent_num = task.number.split(".")[0]
                    if current_top.number == parent_num:
                        current_top.children.append(task)
                    else:
                        # Orphaned subtask -- attach to matching top task
                        for t in reversed(top_tasks):
                            if t.number == parent_num:
                                t.children.append(task)
                                break
                else:
                    # No parent found; still record as top-level
                    top_tasks.append(task)
                    if current_section is not None:
                        current_section.tasks.append(task)
            elif task.level == "leaf":
                # Leaf attaches to matching sub task
                parent_num = ".".join(task.number.split(".")[:2])
                attached = False
                if current_sub is not None and current_sub.number == parent_num:
                    current_sub.children.append(task)
                    attached = True
                if not attached:
                    # Search through top tasks' children
                    for t in reversed(top_tasks):
                        for child in t.children:
                            if child.number == parent_num:
                                child.children.append(task)
                                attached = True
                                break
                        if attached:
                            break

        # Finalize last section
        if current_section is not None:
            current_section.line_range = (
                current_section.line_number,
                len(self.lines),
            )
            sections.append(current_section)

        # Compute line_range for each task
        self._compute_line_ranges(all_task_entries, sections)

        return ParsedPlan(
            file_path=self.file_path,
            plan_type=self.plan_type,
            sections=sections,
            tasks=top_tasks,
            metadata=metadata,
        )

    def _compute_line_ranges(
        self,
        task_entries: list[tuple[ParsedTask, int]],
        sections: list[ParsedSection],
    ) -> None:
        """Compute line_range for each task.

        A task's range starts at its line_number and ends at the line before
        the next task at the same or higher level, or at the end of its section.
        """
        if not task_entries:
            return

        total_lines = len(self.lines)

        for i, (task, _line_num) in enumerate(task_entries):
            start = task.line_number

            # Find end: next task at same or higher level, or end of file
            end = total_lines
            for j in range(i + 1, len(task_entries)):
                next_task, _ = task_entries[j]
                # Level hierarchy: top > sub > leaf
                level_rank = {"top": 0, "sub": 1, "leaf": 2}
                if level_rank[next_task.level] <= level_rank[task.level]:
                    end = next_task.line_number - 1
                    break

            # Also constrain to section boundary
            for section in sections:
                if (
                    section.line_range[0] <= start <= section.line_range[1]
                    and end > section.line_range[1]
                ):
                    end = section.line_range[1]
                    break

            task.line_range = (start, end)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_plan(
    file_path: Path,
    *,
    plan_type: PlanType | None = None,
) -> ParsedPlan:
    """Parse a plan file and return a structured ParsedPlan.

    Auto-detects plan type if not provided:
      - ``file_path.parent.name == "phases"`` -> COMPLEX (phase file)
      - ``file_path.parent / "phases"`` exists -> COMPLEX (master plan)
      - Otherwise -> SIMPLE
    """
    content = file_path.read_text()

    if plan_type is None:
        if file_path.parent.name == "phases":
            plan_type = PlanType.COMPLEX
        elif file_path.parent.joinpath("phases").is_dir():
            plan_type = PlanType.COMPLEX
        else:
            plan_type = PlanType.SIMPLE

    parser = PlanParser(content, str(file_path), plan_type)
    return parser.parse()


# ---------------------------------------------------------------------------
# Required-sections lists (canonical ordering per template)
# ---------------------------------------------------------------------------

REQUIRED_SECTIONS_PHASE: list[str] = [
    "Detailed Objective",
    "Deliverables Snapshot",
    "Acceptance Gates",
    "Scope",
    "Interfaces & Dependencies",
    "Risks & Mitigations",
    "Decision Log",
    "References",
    "Tasks",
    "Completion Step (Required)",
    "Reviewer Checklist",
]

REQUIRED_SECTIONS_SIMPLE: list[str] = [
    "Objective",
    "Current vs Desired",
    "Scope",
    "Policies & Contracts",
    "Tasks",
    "Acceptance Criteria",
    "Risks & Mitigations",
    "Validation",
    "Artifacts Created",
    "Interfaces & Dependencies",
    "References",
    "Reviewer Checklist",
]

REQUIRED_SECTIONS_MASTER: list[str] = [
    "Executive Summary",
    "Detailed Objective",
    "Quick Navigation",
    "Architecture Overview",
    "Current State",
    "Desired State",
    "Global Risks & Mitigations",
    "Global Acceptance Gates",
    "Dependency Gates",
    "Phases Overview",
    "Decision Log",
    "References",
    "Reviewer Checklist",
]

# Alternative names that map to canonical section names.
# Note: Acceptance Criteria and Acceptance Gates are NOT aliases of each other.
SECTION_ALIASES: dict[str, str] = {
    "Dependencies": "Interfaces & Dependencies",
}


# ---------------------------------------------------------------------------
# Helper: detect plan subtype for verification
# ---------------------------------------------------------------------------

def _is_master_plan(plan: ParsedPlan) -> bool:
    """Return True if the plan is a COMPLEX master plan (not a phase file)."""
    if plan.plan_type != PlanType.COMPLEX:
        return False
    # Has Phases Overview section -> master plan
    section_names = {s.name for s in plan.sections}
    if "Phases Overview" in section_names:
        return True
    # File path not inside phases/ dir -> master plan
    p = Path(plan.file_path)
    if p.parent.name != "phases":
        return True
    return False


def _normalize_section_name(name: str) -> str:
    """Normalize a section name through the alias map."""
    return SECTION_ALIASES.get(name, name)


def _get_required_sections(plan: ParsedPlan) -> list[str]:
    """Return the correct required-sections list for the plan subtype."""
    if plan.plan_type == PlanType.SIMPLE:
        return REQUIRED_SECTIONS_SIMPLE
    if _is_master_plan(plan):
        return REQUIRED_SECTIONS_MASTER
    return REQUIRED_SECTIONS_PHASE


# ---------------------------------------------------------------------------
# Check 1: Required-sections check
# ---------------------------------------------------------------------------


def check_required_sections(plan: ParsedPlan) -> list[PlanVerificationIssue]:
    """Verify the plan contains all required sections in the correct order.

    Reports missing sections as errors and out-of-order sections as warnings.
    """
    issues: list[PlanVerificationIssue] = []
    required = _get_required_sections(plan)

    # Build a list of present section names (normalized)
    present_sections: list[tuple[str, int]] = []  # (canonical_name, line_number)
    for s in plan.sections:
        canonical = _normalize_section_name(s.name)
        present_sections.append((canonical, s.line_number))

    present_names = [name for name, _ in present_sections]
    present_set = set(present_names)

    # Check for missing required sections
    for i, req in enumerate(required):
        if req not in present_set:
            # Find the preceding required section that IS present
            preceding = None
            preceding_line = 0
            for j in range(i - 1, -1, -1):
                if required[j] in present_set:
                    preceding = required[j]
                    for name, ln in present_sections:
                        if name == preceding:
                            preceding_line = ln
                            break
                    break

            if preceding:
                suggestion = (
                    f"Add missing section '## {req}' after line {preceding_line} "
                    f"(after '## {preceding}')"
                )
            else:
                suggestion = f"Add missing section '## {req}' near the top of the plan"

            issues.append(PlanVerificationIssue(
                severity="error",
                message=f"Missing required section: '## {req}'",
                line_number=preceding_line or 1,
                suggestion=suggestion,
            ))

    # Check ordering of present sections
    # Build the subsequence of required sections that are present
    required_present = [r for r in required if r in present_set]
    # Get the order in which they actually appear
    actual_order = [name for name in present_names if name in set(required_present)]

    # Find out-of-order sections by checking if actual_order is a valid ordering
    for i, name in enumerate(actual_order):
        expected_idx = required_present.index(name) if name in required_present else -1
        if expected_idx < 0:
            continue
        # Check if there's a section after this one in actual order that should come before
        for j in range(i + 1, len(actual_order)):
            other = actual_order[j]
            other_idx = required_present.index(other) if other in required_present else -1
            if other_idx < expected_idx:
                # 'other' should come before 'name' but appears after
                name_line = 0
                other_line = 0
                for pname, pln in present_sections:
                    if pname == name and name_line == 0:
                        name_line = pln
                    if pname == other and other_line == 0:
                        other_line = pln

                issues.append(PlanVerificationIssue(
                    severity="warning",
                    message=(
                        f"Section '## {other}' (line {other_line}) appears after "
                        f"'## {name}' (line {name_line}) but should come before it"
                    ),
                    line_number=other_line,
                    suggestion=(
                        f"Move '## {other}' (line {other_line}) to before "
                        f"'## {name}' (line {name_line})"
                    ),
                ))
                break  # Report one ordering issue per section

    return issues


# ---------------------------------------------------------------------------
# Check 2: Task numbering check
# ---------------------------------------------------------------------------


def _collect_all_tasks(tasks: list[ParsedTask]) -> list[ParsedTask]:
    """Recursively collect all tasks into a flat list."""
    result: list[ParsedTask] = []
    for t in tasks:
        result.append(t)
        result.extend(_collect_all_tasks(t.children))
    return result


def check_task_numbering(plan: ParsedPlan) -> list[PlanVerificationIssue]:
    """Verify task numbers are sequential with no gaps or duplicates.

    For master plans, numbering is validated per-phase block.
    """
    issues: list[PlanVerificationIssue] = []

    if _is_master_plan(plan):
        # Partition tasks by phase block
        phase_blocks = _partition_master_tasks_by_phase(plan)
        for _phase_label, block_tasks in phase_blocks:
            issues.extend(_check_numbering_scope(block_tasks))
    else:
        issues.extend(_check_numbering_scope(plan.tasks))

    return issues


def _partition_master_tasks_by_phase(
    plan: ParsedPlan,
) -> list[tuple[str, list[ParsedTask]]]:
    """Split master-plan tasks into per-phase groups.

    Phase blocks in the master plan are delimited by ``### Phase N:`` headings.
    Tasks between two phase headings belong to the same phase.
    """
    content = Path(plan.file_path).read_text() if plan.file_path else ""
    lines = content.splitlines()

    # Find phase heading lines: "### Phase N: ..."
    phase_heading_re = re.compile(r"^### Phase \d+:")
    phase_boundaries: list[int] = []  # 1-indexed line numbers
    for idx, line in enumerate(lines):
        if phase_heading_re.match(line):
            phase_boundaries.append(idx + 1)

    if not phase_boundaries:
        # No phase headings found; treat all tasks as one scope
        return [("all", plan.tasks)]

    # Assign each top-level task to a phase block
    blocks: list[tuple[str, list[ParsedTask]]] = []
    for i, boundary in enumerate(phase_boundaries):
        next_boundary = phase_boundaries[i + 1] if i + 1 < len(phase_boundaries) else float("inf")
        block_tasks = [
            t for t in plan.tasks
            if boundary <= t.line_number < next_boundary
        ]
        blocks.append((f"phase_{i}", block_tasks))

    return blocks


def _check_numbering_scope(tasks: list[ParsedTask]) -> list[PlanVerificationIssue]:
    """Check numbering within a single scope (top-level + subtasks)."""
    issues: list[PlanVerificationIssue] = []

    if not tasks:
        return issues

    # Check top-level numbering
    top_numbers: list[tuple[int, int]] = []  # (number, line)
    for t in tasks:
        try:
            num = int(t.number)
            top_numbers.append((num, t.line_number))
        except ValueError:
            pass

    issues.extend(_check_sequential(top_numbers, "Task"))

    # Check subtask numbering per parent
    for t in tasks:
        if not t.children:
            continue
        sub_numbers: list[tuple[int, int]] = []
        for child in t.children:
            parts = child.number.split(".")
            if len(parts) >= 2:
                try:
                    sub_num = int(parts[1])
                    sub_numbers.append((sub_num, child.line_number))
                except ValueError:
                    pass
        issues.extend(_check_sequential(sub_numbers, f"Subtask of task {t.number}"))

        # Check leaf numbering per subtask
        for child in t.children:
            if not child.children:
                continue
            leaf_numbers: list[tuple[int, int]] = []
            for leaf in child.children:
                parts = leaf.number.split(".")
                if len(parts) >= 3:
                    try:
                        leaf_num = int(parts[2])
                        leaf_numbers.append((leaf_num, leaf.line_number))
                    except ValueError:
                        pass
            issues.extend(
                _check_sequential(leaf_numbers, f"Leaf step of subtask {child.number}")
            )

    return issues


def _check_sequential(
    numbers: list[tuple[int, int]], label: str
) -> list[PlanVerificationIssue]:
    """Check that a list of (number, line) pairs is sequential from 1.

    Reports gaps and duplicates.
    """
    issues: list[PlanVerificationIssue] = []

    if not numbers:
        return issues

    # Check for duplicates
    seen: dict[int, int] = {}  # number -> first line
    for num, line in numbers:
        if num in seen:
            issues.append(PlanVerificationIssue(
                severity="error",
                message=f"Duplicate {label.lower()} number {num} found on lines {seen[num]} and {line}",
                line_number=line,
                suggestion=f"Renumber one of the duplicate {label.lower()} entries ({num}) on lines {seen[num]} and {line}",
            ))
        else:
            seen[num] = line

    # Check for gaps
    sorted_nums = sorted(numbers, key=lambda x: x[0])
    expected = 1
    prev_line = sorted_nums[0][1] if sorted_nums else 0
    for num, line in sorted_nums:
        while expected < num:
            issues.append(PlanVerificationIssue(
                severity="error",
                message=f"{label} {expected} is missing (gap between {expected - 1} and {num})",
                line_number=prev_line,
                suggestion=(
                    f"{label} {expected} is missing between line {prev_line} and "
                    f"line {line} -- add the missing task or renumber"
                ),
            ))
            expected += 1
        expected = num + 1
        prev_line = line

    return issues


# ---------------------------------------------------------------------------
# Check 3: Depth violation check
# ---------------------------------------------------------------------------

# Regex to catch task-like headings at any depth (including ones parser drops)
_RAW_HEADING_TASK_RE = re.compile(r"^(#{2,6}) \[[ x\u2705]\] (\d[\d.]*)")
_RAW_BULLET_TASK_RE = re.compile(r"^\s{2}- \[[ x\u2705]\] (\d+(?:\.\d+)+)\b")


def check_depth_violations(plan: ParsedPlan) -> list[PlanVerificationIssue]:
    """Verify no task numbering exceeds the max allowed depth.

    Phase/simple plans: max depth 3 (N.M.K).
    Master plans: max depth 2 (N.M).
    Also scans raw content for malformed headings the parser dropped.
    """
    issues: list[PlanVerificationIssue] = []
    is_master = _is_master_plan(plan)
    max_depth = 2 if is_master else 3
    plan_label = "master plans" if is_master else (
        "simple plans" if plan.plan_type == PlanType.SIMPLE else "phase plans"
    )

    # Check parsed tasks
    all_tasks = _collect_all_tasks(plan.tasks)
    for t in all_tasks:
        depth = len(t.number.split("."))
        if depth > max_depth:
            issues.append(PlanVerificationIssue(
                severity="error",
                message=(
                    f"Task {t.number} on line {t.line_number} exceeds maximum "
                    f"nesting depth of {max_depth} for {plan_label}"
                ),
                line_number=t.line_number,
                suggestion=(
                    f"Task {t.number} on line {t.line_number} exceeds maximum nesting "
                    f"depth of {max_depth} for {plan_label} -- flatten to a bullet "
                    f"point or restructure"
                ),
            ))

    # Scan raw content for malformed headings the parser might have dropped
    content = Path(plan.file_path).read_text() if plan.file_path and Path(plan.file_path).exists() else ""
    if not content and hasattr(plan, '_raw_content'):
        content = plan._raw_content
    lines = content.splitlines() if content else []
    in_fence = False
    for idx, line in enumerate(lines):
        if CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # Check heading-style tasks
        m = _RAW_HEADING_TASK_RE.match(line)
        if m:
            task_num = m.group(2)
            depth = len(task_num.split("."))
            if depth > max_depth:
                # Only report if not already caught by parsed tasks
                line_num = idx + 1
                already_reported = any(
                    i.line_number == line_num for i in issues
                )
                if not already_reported:
                    issues.append(PlanVerificationIssue(
                        severity="error",
                        message=(
                            f"Task {task_num} on line {line_num} exceeds maximum "
                            f"nesting depth of {max_depth} for {plan_label}"
                        ),
                        line_number=line_num,
                        suggestion=(
                            f"Task {task_num} on line {line_num} exceeds maximum "
                            f"nesting depth of {max_depth} for {plan_label} -- "
                            f"flatten to a bullet point or restructure"
                        ),
                    ))

        # Check bullet-style tasks
        m = _RAW_BULLET_TASK_RE.match(line)
        if m:
            task_num = m.group(1)
            depth = len(task_num.split("."))
            if depth > max_depth:
                line_num = idx + 1
                already_reported = any(
                    i.line_number == line_num for i in issues
                )
                if not already_reported:
                    issues.append(PlanVerificationIssue(
                        severity="error",
                        message=(
                            f"Task {task_num} on line {line_num} exceeds maximum "
                            f"nesting depth of {max_depth} for {plan_label}"
                        ),
                        line_number=line_num,
                        suggestion=(
                            f"Task {task_num} on line {line_num} exceeds maximum "
                            f"nesting depth of {max_depth} for {plan_label} -- "
                            f"flatten to a bullet point or restructure"
                        ),
                    ))

    return issues


# ---------------------------------------------------------------------------
# Check 4: Greppable pattern check
# ---------------------------------------------------------------------------


def check_greppable_patterns(plan: ParsedPlan) -> list[PlanVerificationIssue]:
    """Verify task headings use the correct greppable format.

    - Warns on pre-checked task headings ([x] or [checkmark]).
    - Checks heading depth correctness per plan type.
    - For master plans, N.M.K items produce an error.
    - Scans raw content for wrong-depth headings.
    """
    issues: list[PlanVerificationIssue] = []
    is_master = _is_master_plan(plan)

    # (a) Check parsed tasks for pre-checked status
    for t in plan.tasks:
        if t.checked:
            issues.append(PlanVerificationIssue(
                severity="warning",
                message=f"Task {t.number} on line {t.line_number} is pre-checked",
                line_number=t.line_number,
                suggestion=(
                    f"Change the checkbox on line {t.line_number} from "
                    f"'[x]' or '[\\u2705]' to '[ ]' -- tasks should start unchecked"
                ),
            ))

    # (b) Scan raw content for wrong-depth headings
    content = Path(plan.file_path).read_text() if plan.file_path and Path(plan.file_path).exists() else ""
    lines = content.splitlines() if content else []
    in_fence = False
    in_non_mutable = False

    for idx, line in enumerate(lines):
        if CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        line_num = idx + 1

        # Check heading-style task lines BEFORE section tracking,
        # because ## [ ] N lines match both SECTION_RE and _RAW_HEADING_TASK_RE
        m = _RAW_HEADING_TASK_RE.match(line)

        # Track non-mutable sections (but only if NOT a task heading)
        sm = SECTION_RE.match(line)
        if sm and not m:
            section_name = sm.group(1).strip()
            in_non_mutable = _is_non_mutable_section(section_name)
            continue

        if in_non_mutable:
            continue
        if m:
            hashes = m.group(1)
            task_num = m.group(2)
            depth = len(task_num.split("."))

            # Top-level tasks (no dots) should always use ###
            if depth == 1 and hashes != "###":
                issues.append(PlanVerificationIssue(
                    severity="error",
                    message=(
                        f"Top-level task {task_num} on line {line_num} uses "
                        f"'{hashes}' instead of '###'"
                    ),
                    line_number=line_num,
                    suggestion=(
                        f"Change '{hashes} [' on line {line_num} to "
                        f"'### [' -- top-level tasks must use ### headings"
                    ),
                ))

            # For simple plans: subtasks should use ####
            if plan.plan_type == PlanType.SIMPLE and depth == 2 and hashes != "####":
                # #### is correct for simple subtasks; ### is wrong
                if hashes == "###":
                    pass  # This is a top-level, depth check handles it
                elif hashes not in ("####",):
                    issues.append(PlanVerificationIssue(
                        severity="error",
                        message=(
                            f"Subtask {task_num} on line {line_num} uses "
                            f"'{hashes}' instead of '####'"
                        ),
                        line_number=line_num,
                        suggestion=(
                            f"Change '{hashes} [' on line {line_num} to "
                            f"'#### [' -- simple plan subtasks must use #### headings"
                        ),
                    ))

            # Headings deeper than #### for tasks are always wrong
            if len(hashes) >= 5:
                issues.append(PlanVerificationIssue(
                    severity="error",
                    message=(
                        f"Task {task_num} on line {line_num} uses "
                        f"'{hashes}' heading which is too deep"
                    ),
                    line_number=line_num,
                    suggestion=(
                        f"Change '{hashes} [' on line {line_num} to the "
                        f"correct depth -- tasks should not use ##### or deeper headings"
                    ),
                ))

        # (c) Check bullet-style task lines for master plan depth
        m = _RAW_BULLET_TASK_RE.match(line)
        if m and is_master:
            task_num = m.group(1)
            depth = len(task_num.split("."))
            if depth >= 3:
                issues.append(PlanVerificationIssue(
                    severity="error",
                    message=(
                        f"Task {task_num} on line {line_num} is a sub-subtask "
                        f"in a master plan"
                    ),
                    line_number=line_num,
                    suggestion=(
                        f"Remove task {task_num} on line {line_num} -- "
                        f"sub-subtasks are not allowed in master plan Phases Overview"
                    ),
                ))

        # For simple plans: subtasks should use #### not bullet-style
        if m and plan.plan_type == PlanType.SIMPLE:
            task_num = m.group(1)
            depth = len(task_num.split("."))
            if depth == 2:
                issues.append(PlanVerificationIssue(
                    severity="error",
                    message=(
                        f"Subtask {task_num} on line {line_num} uses bullet "
                        f"format '  - [ ]' instead of heading format '#### [ ]'"
                    ),
                    line_number=line_num,
                    suggestion=(
                        f"Change '  - [ ] {task_num}' on line {line_num} to "
                        f"'#### [ ] {task_num}' -- simple plan subtasks must use #### headings"
                    ),
                ))

    return issues


# ---------------------------------------------------------------------------
# Check 5: Cross-file consistency check
# ---------------------------------------------------------------------------


def check_cross_file_consistency(
    master_plan: ParsedPlan, phase_dir: Path
) -> list[PlanVerificationIssue]:
    """Verify master plan mirrors phase files: titles, numbering, count.

    Compares the master plan's Phases Overview against individual phase files.
    """
    issues: list[PlanVerificationIssue] = []

    if not phase_dir.is_dir():
        issues.append(PlanVerificationIssue(
            severity="error",
            message=f"Phase directory not found: {phase_dir}",
            line_number=1,
            suggestion=f"Create the phases directory at {phase_dir}",
        ))
        return issues

    # Parse all phase files
    phase_files = sorted(phase_dir.glob("phase_*.md"))

    # Partition master tasks by phase block
    phase_blocks = _partition_master_tasks_by_phase(master_plan)

    # Check phase count
    if len(phase_blocks) != len(phase_files):
        issues.append(PlanVerificationIssue(
            severity="error",
            message=(
                f"Master plan declares {len(phase_blocks)} phases but "
                f"{len(phase_files)} phase files exist in {phase_dir.name}/"
            ),
            line_number=1,
            suggestion=(
                f"Master plan declares {len(phase_blocks)} phases but "
                f"{len(phase_files)} phase files exist in {phase_dir.name}/ -- "
                f"add missing phase entries to Phases Overview or remove extra phase files"
            ),
        ))

    # Compare task titles and numbering per phase
    for i, phase_file in enumerate(phase_files):
        phase_plan = parse_plan(phase_file)

        if i >= len(phase_blocks):
            issues.append(PlanVerificationIssue(
                severity="error",
                message=f"Phase file {phase_file.name} has no corresponding section in master plan",
                line_number=1,
                suggestion=f"Add Phase {i} entry to Phases Overview for {phase_file.name}",
            ))
            continue

        _label, master_tasks = phase_blocks[i]

        # Compare top-level task count
        if len(master_tasks) != len(phase_plan.tasks):
            issues.append(PlanVerificationIssue(
                severity="error",
                message=(
                    f"Phase {i} ({phase_file.name}): master has "
                    f"{len(master_tasks)} tasks but phase file has "
                    f"{len(phase_plan.tasks)} tasks"
                ),
                line_number=master_tasks[0].line_number if master_tasks else 1,
                suggestion=(
                    f"Update master plan Phase {i} to mirror the "
                    f"{len(phase_plan.tasks)} tasks from {phase_file.name}"
                ),
            ))

        # Compare individual tasks
        for j in range(min(len(master_tasks), len(phase_plan.tasks))):
            mt = master_tasks[j]
            pt = phase_plan.tasks[j]

            # Check numbering
            if mt.number != pt.number:
                issues.append(PlanVerificationIssue(
                    severity="error",
                    message=(
                        f"Phase {i} task numbering mismatch: master line "
                        f"{mt.line_number} has '{mt.number}' but "
                        f"{phase_file.name} line {pt.line_number} has '{pt.number}'"
                    ),
                    line_number=mt.line_number,
                    suggestion=(
                        f"Fix task numbering: master line {mt.line_number} has "
                        f"'{mt.number}' but {phase_file.name} has '{pt.number}' -- "
                        f"numbers must match exactly"
                    ),
                ))

            # Check titles
            if mt.title != pt.title:
                issues.append(PlanVerificationIssue(
                    severity="error",
                    message=(
                        f"Phase {i} task title mismatch: master line "
                        f"{mt.line_number} has '{mt.title}' but "
                        f"{phase_file.name} line {pt.line_number} has '{pt.title}'"
                    ),
                    line_number=mt.line_number,
                    suggestion=(
                        f"Master plan line {mt.line_number} has '{mt.title}' but "
                        f"{phase_file.name} line {pt.line_number} has '{pt.title}' "
                        f"-- titles must match exactly"
                    ),
                ))

    return issues


# ---------------------------------------------------------------------------
# Check 6: Remaining structural checks
# ---------------------------------------------------------------------------

_REFERENCES_SUBSECTIONS = ["Source Files", "Destination Files", "Related Documentation"]


def check_references_subsections(plan: ParsedPlan) -> list[PlanVerificationIssue]:
    """Verify the References section contains required subsections.

    Missing subsections are warnings, not errors.
    """
    issues: list[PlanVerificationIssue] = []

    # Find the References section
    refs_section = None
    for s in plan.sections:
        if _normalize_section_name(s.name) == "References":
            refs_section = s
            break

    if refs_section is None:
        return issues  # Missing References is caught by required-sections check

    # Read raw content to find ### subsections within the References section
    content = Path(plan.file_path).read_text() if plan.file_path and Path(plan.file_path).exists() else ""
    lines = content.splitlines() if content else []

    start = refs_section.line_range[0]
    end = refs_section.line_range[1]
    subsection_re = re.compile(r"^### (.+)")

    found_subsections: set[str] = set()
    for idx in range(start, min(end, len(lines))):
        m = subsection_re.match(lines[idx])
        if m:
            # Normalize: strip parenthetical hints like "(existing code/docs being modified)"
            raw_name = m.group(1).strip()
            # Match against known subsections by prefix
            for expected in _REFERENCES_SUBSECTIONS:
                if raw_name.startswith(expected):
                    found_subsections.add(expected)
                    break

    for expected in _REFERENCES_SUBSECTIONS:
        if expected not in found_subsections:
            issues.append(PlanVerificationIssue(
                severity="warning",
                message=f"References section is missing '### {expected}' subsection",
                line_number=refs_section.line_number,
                suggestion=(
                    f"Add '### {expected}' subsection under '## References' "
                    f"after line {refs_section.line_number}"
                ),
            ))

    return issues


def check_acceptance_gates(plan: ParsedPlan) -> list[PlanVerificationIssue]:
    """Verify the acceptance section exists and has items.

    Phase plans: ## Acceptance Gates
    Simple plans: ## Acceptance Criteria
    Master plans: ## Global Acceptance Gates
    """
    issues: list[PlanVerificationIssue] = []

    if _is_master_plan(plan):
        expected_section = "Global Acceptance Gates"
    elif plan.plan_type == PlanType.SIMPLE:
        expected_section = "Acceptance Criteria"
    else:
        expected_section = "Acceptance Gates"

    # Find the section
    target_section = None
    for s in plan.sections:
        if _normalize_section_name(s.name) == expected_section:
            target_section = s
            break

    if target_section is None:
        issues.append(PlanVerificationIssue(
            severity="error",
            message=f"Missing required acceptance section: '## {expected_section}'",
            line_number=1,
            suggestion=f"Add '## {expected_section}' section with measurable gate items",
        ))
        return issues

    # Check that the section has at least one checkbox item
    content = Path(plan.file_path).read_text() if plan.file_path and Path(plan.file_path).exists() else ""
    lines = content.splitlines() if content else []

    start = target_section.line_range[0]
    end = target_section.line_range[1]
    checkbox_re = re.compile(r"^\s*- \[[ x\u2705]\]")

    has_items = False
    for idx in range(start, min(end, len(lines))):
        if checkbox_re.match(lines[idx]):
            has_items = True
            break

    if not has_items:
        issues.append(PlanVerificationIssue(
            severity="error",
            message=f"Section '## {expected_section}' has no checkbox items",
            line_number=target_section.line_number,
            suggestion=(
                f"Add at least one '- [ ] Gate N: ...' item to "
                f"'## {expected_section}' on line {target_section.line_number}"
            ),
        ))

    return issues


def check_source_paths(
    plan: ParsedPlan, repo_root: Path
) -> list[PlanVerificationIssue]:
    """Verify that source paths referenced in the plan exist.

    Only checks paths in the ## References / ### Source Files subsection.
    Non-existent paths produce warnings, not errors.
    """
    issues: list[PlanVerificationIssue] = []

    # Find the References section
    refs_section = None
    for s in plan.sections:
        if _normalize_section_name(s.name) == "References":
            refs_section = s
            break

    if refs_section is None:
        return issues

    content = Path(plan.file_path).read_text() if plan.file_path and Path(plan.file_path).exists() else ""
    lines = content.splitlines() if content else []

    start = refs_section.line_range[0]
    end = refs_section.line_range[1]

    # Find the ### Source Files subsection within References
    subsection_re = re.compile(r"^### (.+)")
    in_source_files = False
    source_start = 0
    source_end = end

    for idx in range(start, min(end, len(lines))):
        m = subsection_re.match(lines[idx])
        if m:
            name = m.group(1).strip()
            if name.startswith("Source Files"):
                in_source_files = True
                source_start = idx + 1
            elif in_source_files:
                source_end = idx
                break

    if not in_source_files:
        return issues

    # Extract backtick-quoted paths from Source Files subsection
    backtick_re = re.compile(r"`([^`]+)`")
    for idx in range(source_start, min(source_end, len(lines))):
        line = lines[idx]
        for m in backtick_re.finditer(line):
            path_str = m.group(1)
            # Only treat as a file path if it contains /
            if "/" not in path_str:
                continue
            # Strip trailing description (e.g. "path -- description")
            path_str = path_str.split(" --")[0].strip()
            # Glob patterns like *.py are not real paths to check
            if "*" in path_str:
                continue
            full_path = repo_root / path_str
            if not full_path.exists():
                line_num = idx + 1
                issues.append(PlanVerificationIssue(
                    severity="warning",
                    message=(
                        f"Source path '{path_str}' referenced on line {line_num} "
                        f"does not exist"
                    ),
                    line_number=line_num,
                    suggestion=(
                        f"Source path '{path_str}' referenced on line {line_num} "
                        f"does not exist -- update the reference or remove it"
                    ),
                ))

    return issues


def check_task_descriptions(plan: ParsedPlan) -> list[PlanVerificationIssue]:
    """Verify top-level tasks have descriptive text.

    Skipped for master plans (by design, master plan tasks are mirrors only).
    """
    issues: list[PlanVerificationIssue] = []

    if _is_master_plan(plan):
        return issues

    content = Path(plan.file_path).read_text() if plan.file_path and Path(plan.file_path).exists() else ""
    lines = content.splitlines() if content else []

    for task in plan.tasks:
        start = task.line_number  # 1-indexed, this is the heading line
        end = task.line_range[1] if task.line_range[1] > 0 else len(lines)

        # Find first subtask line after the heading
        first_child_line = end
        if task.children:
            first_child_line = min(c.line_number for c in task.children)

        # Check if there is non-blank, non-separator text between heading and first child
        has_description = False
        for idx in range(start, min(first_child_line - 1, len(lines))):
            line = lines[idx].strip()
            if line and line != "---" and not line.startswith("###") and not line.startswith("####"):
                has_description = True
                break

        if not has_description:
            issues.append(PlanVerificationIssue(
                severity="warning",
                message=f"Task {task.number} on line {task.line_number} has no description",
                line_number=task.line_number,
                suggestion=(
                    f"Task {task.number} on line {task.line_number} has no description "
                    f"-- add a brief description after the heading"
                ),
            ))

    return issues


# ---------------------------------------------------------------------------
# verify_plan_syntax() — public aggregation function
# ---------------------------------------------------------------------------


def verify_plan_syntax(
    target: Path,
    *,
    settings: OrchestratorSettings | None = None,
    plan_type: PlanType | None = None,
    check_cross_file: bool = True,
    validate_source_paths: bool = True,
) -> PlanVerificationResult:
    """Run all verification checks and return an aggregated result.

    Args:
        target: Path to the plan file to verify.
        settings: Optional orchestrator settings for repo root detection.
        plan_type: Override for plan type auto-detection.
        check_cross_file: Whether to run cross-file consistency checks.
        validate_source_paths: Whether to check that referenced source paths exist.

    Returns:
        PlanVerificationResult with all issues and pass/fail status.
    """
    plan = parse_plan(target, plan_type=plan_type)
    all_issues: list[PlanVerificationIssue] = []

    # Run all single-file checks
    all_issues.extend(check_required_sections(plan))
    all_issues.extend(check_task_numbering(plan))
    all_issues.extend(check_depth_violations(plan))
    all_issues.extend(check_greppable_patterns(plan))
    all_issues.extend(check_acceptance_gates(plan))
    all_issues.extend(check_references_subsections(plan))

    # Task descriptions check (skip for master plans)
    if not _is_master_plan(plan):
        all_issues.extend(check_task_descriptions(plan))

    # Cross-file consistency (only for master plans)
    if check_cross_file and plan.plan_type == PlanType.COMPLEX and _is_master_plan(plan):
        phase_dir = target.parent / "phases"
        if phase_dir.is_dir():
            all_issues.extend(check_cross_file_consistency(plan, phase_dir))

    # Source path existence check
    if validate_source_paths:
        if settings is not None:
            repo_root = settings.repo_root
        else:
            # Auto-detect repo root: walk up from target
            repo_root = target.parent
            while repo_root != repo_root.parent:
                if (repo_root / ".git").is_dir():
                    break
                repo_root = repo_root.parent

        all_issues.extend(check_source_paths(plan, repo_root))

    # Sort by line number
    all_issues.sort(key=lambda i: i.line_number or 0)

    # Compute pass/fail
    error_count = sum(1 for i in all_issues if i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    passed = error_count == 0

    if passed and warning_count == 0:
        summary = "PASSED (0 errors, 0 warnings)"
    elif passed:
        summary = f"PASSED (0 errors, {warning_count} warning{'s' if warning_count != 1 else ''})"
    else:
        summary = (
            f"{error_count} error{'s' if error_count != 1 else ''}, "
            f"{warning_count} warning{'s' if warning_count != 1 else ''}"
        )

    return PlanVerificationResult(
        passed=passed,
        issues=all_issues,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Status & Query: Data models
# ---------------------------------------------------------------------------


class PhaseProgress(BaseModel):
    """Per-phase progress breakdown."""

    phase: int
    name: str
    total_tasks: int
    completed_tasks: int


class ProgressSummary(BaseModel):
    """Aggregated campaign progress summary."""

    slug: str
    current_phase: int
    current_task: int
    total_phases: int
    total_tasks: int
    total_completed: int
    percent: float
    phase_breakdown: list[PhaseProgress]

    def to_json(self) -> dict:
        """Return a dict suitable for ``json.dumps()``."""
        return {
            "slug": self.slug,
            "current_phase": self.current_phase,
            "current_task": self.current_task,
            "total_phases": self.total_phases,
            "total_tasks": self.total_tasks,
            "total_completed": self.total_completed,
            "percent": self.percent,
            "phase_breakdown": [
                {
                    "phase": p.phase,
                    "name": p.name,
                    "total_tasks": p.total_tasks,
                    "completed_tasks": p.completed_tasks,
                }
                for p in self.phase_breakdown
            ],
        }

    def to_text(self) -> str:
        """Return a compact human-readable status line."""
        return (
            f"{self.slug}: Phase {self.current_phase + 1}/{self.total_phases}, "
            f"Task {self.current_task}/{self.total_tasks} "
            f"({self.percent:.0f}%)"
        )


# ---------------------------------------------------------------------------
# Status & Query: plan_status()
# ---------------------------------------------------------------------------


def _count_tasks_from_plan(
    plan_file: Path,
    plan_type: PlanType,
    settings: OrchestratorSettings,
) -> list[PhaseProgress]:
    """Parse plan file(s) and return per-phase task counts.

    For complex plans, parses each phase file individually.
    For simple plans, parses the single plan file.
    Task counting is marker-agnostic (counts ``[ ]``, ``[x]``, ``[checkmark]``).
    """
    from orchestrator_v3.artifacts import ArtifactResolver

    phases: list[PhaseProgress] = []

    if plan_type == PlanType.COMPLEX:
        phases_dir = plan_file.parent / "phases"
        if phases_dir.is_dir():
            phase_files = sorted(
                phases_dir.glob("phase_*.md"),
                key=lambda p: int(re.search(r"phase_(\d+)_", p.name).group(1))
                if re.search(r"phase_(\d+)_", p.name)
                else 0,
            )
            for i, pf in enumerate(phase_files):
                parsed = parse_plan(pf, plan_type=PlanType.COMPLEX)
                top_tasks = [t for t in parsed.tasks if t.level == "top"]
                # Extract phase name from file stem
                stem = pf.stem
                name_match = re.search(r"phase_\d+_(.*)", stem)
                name = name_match.group(1).replace("_", " ").title() if name_match else f"Phase {i}"
                phases.append(PhaseProgress(
                    phase=i,
                    name=name,
                    total_tasks=len(top_tasks),
                    completed_tasks=0,
                ))
        if not phases:
            phases.append(PhaseProgress(phase=0, name="Main", total_tasks=0, completed_tasks=0))
    else:
        # Simple plan: all tasks in one phase
        parsed = parse_plan(plan_file, plan_type=PlanType.SIMPLE)
        top_tasks = [t for t in parsed.tasks if t.level == "top"]
        phases.append(PhaseProgress(
            phase=0,
            name="Main",
            total_tasks=len(top_tasks),
            completed_tasks=0,
        ))

    return phases


def plan_status(slug: str, settings: OrchestratorSettings) -> ProgressSummary:
    """Compute progress summary for a campaign.

    State loading fallback chain:
      1. ``CampaignIndex`` via ``campaign_index_path()``
      2. ``OrchestratorState`` via ``reviews/{slug}_orchestrator_state.json``
      3. Parse plan file directly with zero-progress defaults

    Task counts are always derived from plan file parsing (never from
    ``CampaignIndex.tasks_per_phase``) to work around the simple plan
    ``tasks_per_phase={"0": 1}`` bug.
    """
    from orchestrator_v3.artifacts import ArtifactResolver
    from orchestrator_v3.state import (
        CampaignIndex,
        CampaignManager,
        OrchestratorState,
        StateManager,
        TaskStateManager,
        campaign_index_path,
        task_state_path,
    )

    # --- Step 1: Load state (fallback chain) ---
    current_phase = 0
    current_task = 1
    campaign_status = None
    plan_file_from_state = None

    ci_path = campaign_index_path(slug, settings)
    orch_state_path = settings.reviews_dir / f"{slug}_orchestrator_state.json"

    if ci_path.exists():
        cm = CampaignManager(state_path=ci_path, settings=settings)
        ci = cm.load()
        current_phase = ci.current_phase
        current_task = ci.current_task
        campaign_status = ci.status
        plan_file_from_state = ci.plan_file
    elif orch_state_path.exists():
        sm = StateManager(state_path=orch_state_path, settings=settings)
        os_state = sm.load()
        current_phase = os_state.current_phase
        current_task = os_state.current_task
        campaign_status = os_state.status
        plan_file_from_state = os_state.plan_file
    # else: fall through with zero-progress defaults

    # --- Step 2: Locate plan file ---
    plan_file: Path | None = None
    try:
        ar = ArtifactResolver(
            slug=slug, mode=Mode.CODE, phase=0, task=1, settings=settings
        )
        plan_file = ar.find_plan_file()
    except FileNotFoundError:
        if plan_file_from_state and Path(plan_file_from_state).exists():
            plan_file = Path(plan_file_from_state)

    if plan_file is None:
        raise FileNotFoundError(
            f"No plan file found for slug '{slug}'. "
            f"Tried active_plans/{slug}/ and state files."
        )

    # --- Step 3: Parse plan for true task counts ---
    ar = ArtifactResolver(
        slug=slug, mode=Mode.CODE, phase=0, task=1, settings=settings
    )
    plan_type = ar.detect_plan_type()
    phase_breakdown = _count_tasks_from_plan(plan_file, plan_type, settings)

    # --- Step 4: Campaign-level completion override ---
    if campaign_status in ("complete", "approved"):
        for pb in phase_breakdown:
            pb.completed_tasks = pb.total_tasks
    else:
        # --- Step 5: Scan per-task state files for completion ---
        for pb in phase_breakdown:
            completed = 0
            for task_num in range(1, pb.total_tasks + 1):
                ts_path = task_state_path(slug, pb.phase, task_num, settings)
                if ts_path.exists():
                    try:
                        tsm = TaskStateManager(state_path=ts_path)
                        ts = tsm.load()
                        if ts.status in ("approved", "complete"):
                            completed += 1
                    except Exception:
                        pass
            pb.completed_tasks = completed

    # --- Step 6: Compute totals ---
    total_tasks = sum(p.total_tasks for p in phase_breakdown)
    total_completed = sum(p.completed_tasks for p in phase_breakdown)
    percent = (total_completed / total_tasks * 100.0) if total_tasks > 0 else 0.0

    return ProgressSummary(
        slug=slug,
        current_phase=current_phase,
        current_task=current_task,
        total_phases=len(phase_breakdown),
        total_tasks=total_tasks,
        total_completed=total_completed,
        percent=percent,
        phase_breakdown=phase_breakdown,
    )


# ---------------------------------------------------------------------------
# Status & Query: plan_show()
# ---------------------------------------------------------------------------


def plan_show(
    slug: str,
    settings: OrchestratorSettings,
    *,
    current: bool = False,
    recent: bool = False,
) -> str:
    """Extract and format task information from a plan.

    Modes:
      - ``current=True``: extract current task subtree from plan
      - ``recent=True``: show last N approved tasks sorted by timestamp
      - default: full task list with status icons

    Returns:
        Formatted text string.
    """
    from orchestrator_v3.artifacts import ArtifactResolver
    from orchestrator_v3.state import (
        CampaignManager,
        StateManager,
        TaskStateManager,
        campaign_index_path,
        task_state_path,
    )

    # Load state for phase/task pointer
    current_phase = 0
    current_task_num = 1

    ci_path = campaign_index_path(slug, settings)
    orch_state_path = settings.reviews_dir / f"{slug}_orchestrator_state.json"

    if ci_path.exists():
        cm = CampaignManager(state_path=ci_path, settings=settings)
        ci = cm.load()
        current_phase = ci.current_phase
        current_task_num = ci.current_task
    elif orch_state_path.exists():
        sm = StateManager(state_path=orch_state_path, settings=settings)
        os_state = sm.load()
        current_phase = os_state.current_phase
        current_task_num = os_state.current_task

    # Locate plan file
    ar = ArtifactResolver(
        slug=slug, mode=Mode.CODE, phase=0, task=1, settings=settings
    )
    plan_file = ar.find_plan_file()
    plan_type = ar.detect_plan_type()

    if current:
        return _plan_show_current(
            plan_file, plan_type, current_phase, current_task_num, settings
        )
    elif recent:
        return _plan_show_recent(slug, plan_file, plan_type, settings)
    else:
        return _plan_show_default(slug, plan_file, plan_type, settings)


def _plan_show_current(
    plan_file: Path,
    plan_type: PlanType,
    phase: int,
    task_num: int,
    settings: OrchestratorSettings,
) -> str:
    """Extract the current task subtree from the plan file."""
    # For complex plans, parse the phase file directly
    if plan_type == PlanType.COMPLEX:
        phases_dir = plan_file.parent / "phases"
        if phases_dir.is_dir():
            phase_files = sorted(
                phases_dir.glob("phase_*.md"),
                key=lambda p: int(re.search(r"phase_(\d+)_", p.name).group(1))
                if re.search(r"phase_(\d+)_", p.name)
                else 0,
            )
            if phase < len(phase_files):
                target_file = phase_files[phase]
            else:
                return f"Warning: Phase {phase} not found (plan has {len(phase_files)} phases)"
        else:
            return "Warning: phases/ directory not found for complex plan"
    else:
        target_file = plan_file

    parsed = parse_plan(target_file, plan_type=plan_type)
    top_tasks = [t for t in parsed.tasks if t.level == "top"]

    # Find the task matching the task number
    target_task = None
    for t in top_tasks:
        try:
            if int(t.number) == task_num:
                target_task = t
                break
        except ValueError:
            continue

    if target_task is None:
        return (
            f"Warning: Task {task_num} not found in phase {phase}. "
            f"State pointer may be stale."
        )

    # Extract the task subtree text from the file
    lines = target_file.read_text().splitlines()
    start = target_task.line_range[0] - 1  # 0-indexed
    end = target_task.line_range[1]  # inclusive, but line_range is 1-indexed
    task_lines = lines[start:end]

    return "\n".join(task_lines)


def _plan_show_recent(
    slug: str,
    plan_file: Path,
    plan_type: PlanType,
    settings: OrchestratorSettings,
    n: int = 5,
) -> str:
    """Show the last N approved tasks sorted by timestamp."""
    from orchestrator_v3.state import TaskStateManager, task_state_path

    # Get task counts per phase
    phase_breakdown = _count_tasks_from_plan(plan_file, plan_type, settings)

    # Build task title lookup
    task_titles: dict[tuple[int, int], str] = {}
    if plan_type == PlanType.COMPLEX:
        phases_dir = plan_file.parent / "phases"
        if phases_dir.is_dir():
            phase_files = sorted(
                phases_dir.glob("phase_*.md"),
                key=lambda p: int(re.search(r"phase_(\d+)_", p.name).group(1))
                if re.search(r"phase_(\d+)_", p.name)
                else 0,
            )
            for i, pf in enumerate(phase_files):
                parsed = parse_plan(pf, plan_type=PlanType.COMPLEX)
                for t in parsed.tasks:
                    if t.level == "top":
                        try:
                            task_titles[(i, int(t.number))] = t.title
                        except ValueError:
                            pass
    else:
        parsed = parse_plan(plan_file, plan_type=PlanType.SIMPLE)
        for t in parsed.tasks:
            if t.level == "top":
                try:
                    task_titles[(0, int(t.number))] = t.title
                except ValueError:
                    pass

    # Collect approved history entries across all tasks
    approved_entries: list[tuple[str, int, int, str, int]] = []  # (timestamp, phase, task, title, round)
    for pb in phase_breakdown:
        for task_num in range(1, pb.total_tasks + 1):
            ts_path = task_state_path(slug, pb.phase, task_num, settings)
            if ts_path.exists():
                try:
                    tsm = TaskStateManager(state_path=ts_path)
                    ts = tsm.load()
                    for entry in ts.history:
                        if entry.get("outcome") == "approved":
                            timestamp = entry.get("timestamp", "")
                            title = task_titles.get((pb.phase, task_num), f"Task {task_num}")
                            round_num = entry.get("round", 0)
                            approved_entries.append(
                                (timestamp, pb.phase, task_num, title, round_num)
                            )
                except Exception:
                    pass

    if not approved_entries:
        return "No approved tasks found."

    # Sort by timestamp descending and take first N
    approved_entries.sort(key=lambda x: x[0], reverse=True)
    recent = approved_entries[:n]

    lines = []
    for ts, phase, task_num, title, round_num in recent:
        lines.append(f"Phase {phase} Task {task_num}: {title} (round {round_num})")

    return "\n".join(lines)


def _plan_show_default(
    slug: str,
    plan_file: Path,
    plan_type: PlanType,
    settings: OrchestratorSettings,
) -> str:
    """Show full task list with status icons."""
    from orchestrator_v3.state import TaskStateManager, task_state_path

    lines: list[str] = []

    if plan_type == PlanType.COMPLEX:
        phases_dir = plan_file.parent / "phases"
        if phases_dir.is_dir():
            phase_files = sorted(
                phases_dir.glob("phase_*.md"),
                key=lambda p: int(re.search(r"phase_(\d+)_", p.name).group(1))
                if re.search(r"phase_(\d+)_", p.name)
                else 0,
            )
            for i, pf in enumerate(phase_files):
                parsed = parse_plan(pf, plan_type=PlanType.COMPLEX)
                top_tasks = [t for t in parsed.tasks if t.level == "top"]
                # Phase header from file stem
                stem = pf.stem
                name_match = re.search(r"phase_\d+_(.*)", stem)
                name = name_match.group(1).replace("_", " ").title() if name_match else f"Phase {i}"
                lines.append(f"Phase {i}: {name}")
                for t in top_tasks:
                    try:
                        tn = int(t.number)
                    except ValueError:
                        tn = 0
                    status_icon = _task_status_icon(slug, i, tn, settings)
                    lines.append(f"  {status_icon} {t.number} {t.title}")
    else:
        parsed = parse_plan(plan_file, plan_type=PlanType.SIMPLE)
        top_tasks = [t for t in parsed.tasks if t.level == "top"]
        for t in top_tasks:
            try:
                tn = int(t.number)
            except ValueError:
                tn = 0
            status_icon = _task_status_icon(slug, 0, tn, settings)
            lines.append(f"{status_icon} {t.number} {t.title}")

    return "\n".join(lines) if lines else "No tasks found."


def _task_status_icon(
    slug: str, phase: int, task_num: int, settings: OrchestratorSettings
) -> str:
    """Return a status icon for a task based on its per-task state file."""
    from orchestrator_v3.state import TaskStateManager, task_state_path

    ts_path = task_state_path(slug, phase, task_num, settings)
    if ts_path.exists():
        try:
            tsm = TaskStateManager(state_path=ts_path)
            ts = tsm.load()
            if ts.status in ("approved", "complete"):
                return "[completed]"
            else:
                return "[in progress]"
        except Exception:
            pass
    return "[pending]"


# ---------------------------------------------------------------------------
# Write Operations: plan_sync, plan_render_master, plan_reconcile
# ---------------------------------------------------------------------------


def _find_phase_file(slug: str, phase: int, settings: OrchestratorSettings) -> Path:
    """Locate a phase file matching ``phase_{phase}_*.md`` for a slug.

    Raises:
        FileNotFoundError: If no matching phase file is found.
    """
    phases_dir = settings.active_plans_dir / slug / "phases"
    if not phases_dir.is_dir():
        raise FileNotFoundError(
            f"Phases directory not found: {phases_dir}"
        )
    pattern = f"phase_{phase}_*.md"
    matches = list(phases_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No phase file matching '{pattern}' in {phases_dir}"
        )
    return matches[0]


def _atomic_write(target: Path, content: str) -> None:
    """Write content to target atomically via temp file + os.replace()."""
    os.makedirs(target.parent, exist_ok=True)
    fd = tempfile.NamedTemporaryFile(
        mode="w",
        dir=target.parent,
        suffix=".tmp",
        delete=False,
    )
    try:
        fd.write(content)
        fd.close()
        os.replace(fd.name, target)
    except BaseException:
        fd.close()
        try:
            os.unlink(fd.name)
        except OSError:
            pass
        raise


def plan_sync(
    slug: str,
    phase: int,
    task: int,
    settings: OrchestratorSettings,
    *,
    dry_run: bool = False,
) -> SyncResult:
    """Mark a single approved task complete in its phase file.

    Toggles checkmarks for the target task heading, all subtasks, and all
    leaf steps within the canonical task section of the phase file.
    Section-aware: does not modify checkmarks in Acceptance Gates, Scope,
    Reviewer Checklist, or code fences.

    Args:
        slug: Project slug.
        phase: Phase number.
        task: Task number to mark complete.
        settings: Orchestrator settings.
        dry_run: If True, report what would change without writing.

    Returns:
        SyncResult with change details.

    Raises:
        FileNotFoundError: If the phase file does not exist.
        ValueError: If the task number is not found in the phase file.
    """
    phase_file = _find_phase_file(slug, phase, settings)
    content = phase_file.read_text()
    lines = content.splitlines()

    # Parse to get section-aware boundaries
    parser = PlanParser(content, str(phase_file), PlanType.COMPLEX)
    parsed = parser.parse()

    # Build set of line numbers in non-mutable sections or code fences
    non_mutable_lines: set[int] = set()
    for section in parsed.sections:
        if _is_non_mutable_section(section.name) or section.name == "Scope":
            start = section.line_range[0]
            end = section.line_range[1]
            for ln in range(start, end + 1):
                non_mutable_lines.add(ln)

    # Also track code fences by scanning raw content
    in_fence = False
    for idx, line in enumerate(lines):
        if CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            non_mutable_lines.add(idx + 1)
            continue
        if in_fence:
            non_mutable_lines.add(idx + 1)

    # Regex patterns for matching task heading and subtasks
    task_heading_re = re.compile(
        rf"^### \[[ x\u2705]\] {task}\s"
    )
    subtask_re = re.compile(
        rf"^\s{{2}}- \[[ x\u2705]\] {task}\.\d+\s"
    )
    leaf_re = re.compile(
        rf"^\s{{4}}- \[[ x\u2705]\] {task}\.\d+\.\d+\s"
    )
    # Already-checked patterns
    task_heading_checked_re = re.compile(
        rf"^### \[[x\u2705]\] {task}\s"
    )

    # Find the task heading
    task_heading_line = None
    for idx, line in enumerate(lines):
        ln = idx + 1  # 1-indexed
        if ln in non_mutable_lines:
            continue
        if task_heading_re.match(line):
            task_heading_line = idx
            break

    if task_heading_line is None:
        raise ValueError(
            f"Task {task} not found in phase file {phase_file.name}. "
            f"Available tasks: "
            + ", ".join(str(t.number) for t in parsed.tasks if t.level == "top")
        )

    # Check idempotency: if already checked, return 0 changes
    if task_heading_checked_re.match(lines[task_heading_line]):
        return SyncResult(
            files_updated=0,
            checkmarks_toggled=0,
            dry_run=dry_run,
            details=["Task already marked complete"],
        )

    # Collect all lines to toggle (heading + subtasks + leaf steps)
    toggle_indices: list[int] = []
    details: list[str] = []

    # Toggle the heading
    toggle_indices.append(task_heading_line)

    # Find subtasks and leaf steps that belong to this task
    # They must come after the heading and before the next top-level task
    for idx in range(task_heading_line + 1, len(lines)):
        ln = idx + 1
        if ln in non_mutable_lines:
            continue
        line = lines[idx]
        # Stop at next top-level task heading
        if COMPLEX_TOP_RE.match(line):
            break
        # Stop at next section heading
        if SECTION_RE.match(line):
            break
        if subtask_re.match(line):
            toggle_indices.append(idx)
        elif leaf_re.match(line):
            toggle_indices.append(idx)

    # Toggle checkmarks
    new_lines = list(lines)
    toggled = 0
    for idx in toggle_indices:
        line = new_lines[idx]
        # Replace [ ] with [checkmark]
        new_line = re.sub(r"\[ \]", "[\u2705]", line, count=1)
        if new_line != line:
            details.append(f"Line {idx + 1}: {line.strip()} -> {new_line.strip()}")
            new_lines[idx] = new_line
            toggled += 1

    if dry_run:
        return SyncResult(
            files_updated=1 if toggled > 0 else 0,
            checkmarks_toggled=toggled,
            dry_run=True,
            details=details,
        )

    if toggled > 0:
        new_content = "\n".join(new_lines)
        # Preserve trailing newline if original had one
        if content.endswith("\n"):
            new_content += "\n"
        _atomic_write(phase_file, new_content)

    return SyncResult(
        files_updated=1 if toggled > 0 else 0,
        checkmarks_toggled=toggled,
        dry_run=False,
        details=details,
    )


def plan_render_master(
    slug: str,
    settings: OrchestratorSettings,
    *,
    dry_run: bool = False,
) -> SyncResult:
    """Regenerate the master plan's Phases Overview from phase file state.

    Globs all phase files, extracts task headings and first-level subtasks
    (no descriptions, no sub-sub-tasks), and replaces the Phases Overview
    section in the master plan.

    Args:
        slug: Project slug.
        settings: Orchestrator settings.
        dry_run: If True, report what would change without writing.

    Returns:
        SyncResult with change details.

    Raises:
        FileNotFoundError: If master plan or phases directory not found.
    """
    from orchestrator_v3.artifacts import ArtifactResolver

    ar = ArtifactResolver(
        slug=slug, mode=Mode.CODE, phase=0, task=1, settings=settings
    )
    master_file = ar.find_plan_file()
    phases_dir = settings.active_plans_dir / slug / "phases"

    if not phases_dir.is_dir():
        raise FileNotFoundError(f"Phases directory not found: {phases_dir}")

    # Sort phase files by phase number
    phase_files = sorted(
        phases_dir.glob("phase_*.md"),
        key=lambda p: int(re.search(r"phase_(\d+)_", p.name).group(1))
        if re.search(r"phase_(\d+)_", p.name)
        else 0,
    )

    # Build Phases Overview content from phase files
    overview_lines: list[str] = []
    total_items = 0
    details: list[str] = []

    for pf in phase_files:
        parsed = parse_plan(pf, plan_type=PlanType.COMPLEX)
        details.append(f"Read: {pf.name}")

        # Extract phase number and title from the # heading
        phase_title = ""
        phase_num = 0
        m = re.search(r"phase_(\d+)_", pf.name)
        if m:
            phase_num = int(m.group(1))

        raw_lines = pf.read_text().splitlines()
        for line in raw_lines:
            h1_match = re.match(r"^# Phase (\d+): (.+)", line)
            if h1_match:
                phase_title = h1_match.group(2).strip()
                break

        if not phase_title:
            stem = pf.stem
            name_match = re.search(r"phase_\d+_(.*)", stem)
            phase_title = name_match.group(1).replace("_", " ").title() if name_match else f"Phase {phase_num}"

        # Phase sub-heading with relative path
        rel_path = pf.relative_to(settings.active_plans_dir.parent) if settings.active_plans_dir.parent in pf.parents else pf.name
        overview_lines.append(f"### Phase {phase_num}: {phase_title} \u2014 {rel_path}")
        overview_lines.append("")
        overview_lines.append("#### Tasks")
        overview_lines.append("")

        # Extract task headings and first-level subtasks only
        for task in parsed.tasks:
            if task.level != "top":
                continue
            check = "\u2705" if task.checked else " "
            overview_lines.append(f"### [{check}] {task.number} {task.title}")
            total_items += 1
            for child in task.children:
                if child.level == "sub":
                    child_check = "\u2705" if child.checked else " "
                    overview_lines.append(f"  - [{child_check}] {child.number} {child.title}")
                    total_items += 1

        overview_lines.append("")

    # Read master plan and find Phases Overview section
    master_content = master_file.read_text()
    master_lines = master_content.splitlines()

    overview_start = None
    overview_end = None
    for idx, line in enumerate(master_lines):
        if re.match(r"^## Phases Overview", line):
            overview_start = idx
        elif overview_start is not None and re.match(r"^## ", line):
            overview_end = idx
            break

    if overview_start is None:
        raise FileNotFoundError(
            f"'## Phases Overview' section not found in {master_file}"
        )

    if overview_end is None:
        overview_end = len(master_lines)

    # Build new master content: preserve header, replace overview, preserve footer
    new_master_lines = (
        master_lines[:overview_start + 1]  # Include "## Phases Overview" heading
        + [""]
        + overview_lines
        + master_lines[overview_end:]
    )

    new_content = "\n".join(new_master_lines)
    if master_content.endswith("\n"):
        new_content += "\n"

    if dry_run:
        return SyncResult(
            files_updated=1,
            checkmarks_toggled=total_items,
            dry_run=True,
            details=details,
        )

    _atomic_write(master_file, new_content)

    return SyncResult(
        files_updated=1,
        checkmarks_toggled=total_items,
        dry_run=False,
        details=details,
    )


def plan_reconcile(
    slug: str,
    settings: OrchestratorSettings,
    *,
    apply: bool = False,
    from_reviews: bool = False,
) -> DriftReport:
    """Compare orchestrator state files against plan checkmarks to detect drift.

    Builds ``state_completed`` from per-task state files (and optionally
    review artifacts), builds ``plan_completed`` from parsed plan checkmarks,
    and computes the symmetric difference.

    Args:
        slug: Project slug.
        settings: Orchestrator settings.
        apply: If True, call plan_sync for each missing_in_plan entry.
        from_reviews: If True, also infer completion from review file verdicts.

    Returns:
        DriftReport with drift details.
    """
    from orchestrator_v3.approval import Verdict, parse_orch_meta
    from orchestrator_v3.artifacts import ArtifactResolver

    # --- Build state_completed set ---
    state_completed: set[tuple[int, int]] = set()

    # Scan per-task state files
    if settings.reviews_dir.is_dir():
        state_re = re.compile(
            rf"^{re.escape(slug)}_p(\d+)_t(\d+)_state\.json$"
        )
        for f in settings.reviews_dir.iterdir():
            m = state_re.match(f.name)
            if m:
                try:
                    from orchestrator_v3.state import TaskStateManager

                    tsm = TaskStateManager(state_path=f)
                    ts = tsm.load()
                    if ts.status in ("approved", "complete"):
                        state_completed.add((int(m.group(1)), int(m.group(2))))
                except Exception:
                    logger.warning("Skipping malformed state file: %s", f)

    # Optionally scan review files for APPROVED verdicts
    if from_reviews and settings.reviews_dir.is_dir():
        review_re = re.compile(
            rf"^{re.escape(slug)}_phase_(\d+)_task_(\d+)_code_review_round(\d+)\.md$"
        )
        # Collect highest-round review per (phase, task)
        highest_rounds: dict[tuple[int, int], tuple[int, Path]] = {}
        for f in settings.reviews_dir.iterdir():
            m = review_re.match(f.name)
            if m:
                p, t, r = int(m.group(1)), int(m.group(2)), int(m.group(3))
                key = (p, t)
                if key not in highest_rounds or r > highest_rounds[key][0]:
                    highest_rounds[key] = (r, f)

        for (p, t), (_round, review_file) in highest_rounds.items():
            result = parse_orch_meta(review_file)
            if result is not None and result.verdict == Verdict.APPROVED:
                state_completed.add((p, t))

    # --- Build plan_completed set ---
    plan_completed: set[tuple[int, int]] = set()

    phases_dir = settings.active_plans_dir / slug / "phases"
    if phases_dir.is_dir():
        phase_files = sorted(
            phases_dir.glob("phase_*.md"),
            key=lambda p: int(re.search(r"phase_(\d+)_", p.name).group(1))
            if re.search(r"phase_(\d+)_", p.name)
            else 0,
        )
        for pf in phase_files:
            m = re.search(r"phase_(\d+)_", pf.name)
            if not m:
                continue
            phase_num = int(m.group(1))
            parsed = parse_plan(pf, plan_type=PlanType.COMPLEX)
            for task in parsed.tasks:
                if task.level == "top" and task.checked:
                    try:
                        plan_completed.add((phase_num, int(task.number)))
                    except ValueError:
                        pass

    # --- Compute drift ---
    missing_in_plan = state_completed - plan_completed
    missing_in_state = plan_completed - state_completed
    in_sync = len(missing_in_plan) == 0 and len(missing_in_state) == 0

    # --- Optionally apply fixes ---
    if apply and missing_in_plan:
        for p, t in sorted(missing_in_plan):
            try:
                plan_sync(slug, p, t, settings)
            except (FileNotFoundError, ValueError) as e:
                logger.warning("plan_sync failed for (phase=%d, task=%d): %s", p, t, e)
        try:
            plan_render_master(slug, settings)
        except Exception as e:
            logger.warning("plan_render_master failed: %s", e)

    return DriftReport(
        in_sync=in_sync,
        state_completed=frozenset(state_completed),
        plan_completed=frozenset(plan_completed),
        missing_in_plan=frozenset(missing_in_plan),
        missing_in_state=frozenset(missing_in_state),
    )
