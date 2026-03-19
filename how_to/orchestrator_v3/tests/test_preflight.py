"""Tests for preflight validation module.

Phase 1, Task 2: Verify each individual check function and the
aggregate runners for code and plan modes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator_v3.preflight import (
    CheckResult,
    PreflightResult,
    check_artifact_exists,
    check_code_diff_fences,
    check_code_file_headings,
    check_code_test_lines,
    check_minimum_size,
    run_code_preflight,
    run_plan_preflight,
)


# ── check_artifact_exists ─────────────────────────────────────────────


class TestCheckArtifactExists:
    def test_missing_file(self, tmp_path):
        result = check_artifact_exists(tmp_path / "nope.md")
        assert not result.passed
        assert "not found" in result.message

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        result = check_artifact_exists(f)
        assert not result.passed
        assert "empty" in result.message.lower()

    def test_nonempty_file(self, tmp_path):
        f = tmp_path / "ok.md"
        f.write_text("content\n")
        result = check_artifact_exists(f)
        assert result.passed


# ── check_code_file_headings ──────────────────────────────────────────


class TestCheckCodeFileHeadings:
    def test_has_file_heading(self):
        result = check_code_file_headings("File: src/main.py\n")
        assert result.passed

    def test_has_markdown_file_heading(self):
        result = check_code_file_headings("### File: src/main.py\n")
        assert result.passed

    def test_no_file_heading(self):
        result = check_code_file_headings("No headings here\n")
        assert not result.passed
        assert "File:" in result.message

    def test_file_heading_mid_content(self):
        content = "# Header\n\nSome text\n\nFile: path/to/file.py\n\nmore\n"
        result = check_code_file_headings(content)
        assert result.passed


# ── check_code_diff_fences ────────────────────────────────────────────


class TestCheckCodeDiffFences:
    def test_has_diff_fence(self):
        result = check_code_diff_fences("~~~diff\n+added\n~~~\n")
        assert result.passed

    def test_has_python_fence(self):
        result = check_code_diff_fences("~~~python\nprint('hi')\n~~~\n")
        assert result.passed

    def test_no_fence(self):
        result = check_code_diff_fences("No fences here\n")
        assert not result.passed
        assert "~~~diff" in result.message

    def test_backtick_fence_not_accepted(self):
        result = check_code_diff_fences("```diff\n+added\n```\n")
        assert not result.passed


# ── check_code_test_lines ─────────────────────────────────────────────


class TestCheckCodeTestLines:
    def test_has_test_line(self):
        result = check_code_test_lines("Test: pytest tests/ -q\n")
        assert result.passed

    def test_has_verify_line(self):
        result = check_code_test_lines("Verify: python3 -c 'import mod'\n")
        assert result.passed

    def test_no_test_line(self):
        result = check_code_test_lines("No test lines\n")
        assert not result.passed
        assert "Test:" in result.message

    def test_test_mid_content(self):
        content = "# Results\n\nTest: make check\n\nOutput: ok\n"
        result = check_code_test_lines(content)
        assert result.passed


# ── check_minimum_size ────────────────────────────────────────────────


class TestCheckMinimumSize:
    def test_above_minimum(self):
        content = "\n".join(f"line {i}" for i in range(60))
        result = check_minimum_size(content, min_lines=50)
        assert result.passed

    def test_below_minimum(self):
        result = check_minimum_size("short\n", min_lines=50)
        assert not result.passed
        assert "only 1 lines" in result.message

    def test_exact_minimum(self):
        content = "\n".join(f"line {i}" for i in range(50))
        result = check_minimum_size(content, min_lines=50)
        assert result.passed


# ── run_code_preflight ────────────────────────────────────────────────


class TestRunCodePreflight:
    def test_missing_artifact(self, tmp_path):
        result = run_code_preflight(tmp_path / "nope.md")
        assert not result.passed
        assert len(result.checks) == 1
        assert result.checks[0].name == "artifact_exists"

    def test_malformed_artifact(self, tmp_path):
        """Artifact exists but missing all required elements."""
        f = tmp_path / "bad.md"
        f.write_text("# Bad artifact\nJust text.\n")
        result = run_code_preflight(f)
        assert not result.passed
        failed = [c for c in result.checks if not c.passed]
        assert len(failed) >= 3  # file headings, diff fences, test lines, size

    def test_wellformed_artifact(self, tmp_path):
        """Artifact with all required elements passes."""
        lines = [
            "# Code Complete",
            "",
            "## Summary",
            "Implemented the feature.",
            "",
            "File: src/main.py",
            "",
            "~~~diff",
            "+added line",
            "~~~",
            "",
            "Test: pytest tests/ -q",
            "",
            "~~~",
            "5 passed",
            "~~~",
            "",
        ]
        # Pad to >50 lines
        while len(lines) < 55:
            lines.append(f"# padding line {len(lines)}")
        f = tmp_path / "good.md"
        f.write_text("\n".join(lines))
        result = run_code_preflight(f)
        assert result.passed
        assert all(c.passed for c in result.checks)

    def test_with_template(self):
        """Gate 4: Preflight passes the code_complete_template.md."""
        template = Path(__file__).resolve().parents[2] / "templates" / "code_complete_template.md"
        if not template.exists():
            pytest.skip(f"Template not found: {template}")
        result = run_code_preflight(template)
        # Template has File: headings, ~~~diff fences, Test: lines, and >50 lines
        assert result.passed, (
            "code_complete_template.md should pass code preflight: "
            + "; ".join(c.message for c in result.checks if not c.passed)
        )


# ── run_plan_preflight ────────────────────────────────────────────────


class TestRunPlanPreflight:
    def test_missing_artifact(self, tmp_path):
        result = run_plan_preflight(tmp_path / "nope.md")
        assert not result.passed

    def test_too_short(self, tmp_path):
        f = tmp_path / "short.md"
        f.write_text("# Plan\nBrief.\n")
        result = run_plan_preflight(f)
        assert not result.passed
        failed = [c for c in result.checks if not c.passed]
        assert any("minimum" in c.message.lower() for c in failed)

    def test_adequate_plan(self, tmp_path):
        lines = [f"line {i}" for i in range(25)]
        f = tmp_path / "plan.md"
        f.write_text("\n".join(lines))
        result = run_plan_preflight(f)
        assert result.passed
