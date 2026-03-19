"""Preflight validation for orchestrator_v3.

Runs hardcoded format checks on artifacts before invoking the reviewer,
catching mechanically detectable issues that would waste a review round.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckResult:
    """Result of a single preflight check."""

    name: str
    passed: bool
    message: str


@dataclass
class PreflightResult:
    """Aggregate result of all preflight checks."""

    passed: bool
    checks: list[CheckResult] = field(default_factory=list)


# ── Individual checks ─────────────────────────────────────────────────


def check_artifact_exists(path: Path) -> CheckResult:
    """Check that the artifact file exists and is non-empty."""
    if not path.exists():
        return CheckResult(
            name="artifact_exists",
            passed=False,
            message=f"Artifact not found: {path}",
        )
    if not path.is_file():
        return CheckResult(
            name="artifact_exists",
            passed=False,
            message=f"Artifact is not a regular file: {path}",
        )
    if path.stat().st_size == 0:
        return CheckResult(
            name="artifact_exists",
            passed=False,
            message=f"Artifact is empty: {path}",
        )
    return CheckResult(
        name="artifact_exists",
        passed=True,
        message="Artifact exists and is non-empty.",
    )


def check_code_file_headings(content: str) -> CheckResult:
    """Check that the artifact contains at least one ``File:`` heading."""
    pattern = re.compile(r"^(?:###\s+)?File:\s+", re.MULTILINE)
    if pattern.search(content):
        return CheckResult(
            name="code_file_headings",
            passed=True,
            message="Found File: heading(s).",
        )
    return CheckResult(
        name="code_file_headings",
        passed=False,
        message="No 'File:' headings found. Each modified file needs a 'File: path/to/file' line.",
    )


def check_code_diff_fences(content: str) -> CheckResult:
    """Check that the artifact contains ``~~~diff`` or ``~~~python`` fenced blocks."""
    pattern = re.compile(r"^~~~(?:diff|python)\s*$", re.MULTILINE)
    if pattern.search(content):
        return CheckResult(
            name="code_diff_fences",
            passed=True,
            message="Found ~~~diff or ~~~python fenced block(s).",
        )
    return CheckResult(
        name="code_diff_fences",
        passed=False,
        message="No '~~~diff' or '~~~python' fenced blocks found. Use ~~~diff for unified diffs.",
    )


def check_code_test_lines(content: str) -> CheckResult:
    """Check that the artifact contains ``Test:`` or ``Verify:`` lines."""
    pattern = re.compile(r"^(?:Test|Verify):\s+", re.MULTILINE)
    if pattern.search(content):
        return CheckResult(
            name="code_test_lines",
            passed=True,
            message="Found Test: or Verify: line(s).",
        )
    return CheckResult(
        name="code_test_lines",
        passed=False,
        message="No 'Test:' or 'Verify:' lines found. Show how changes were verified.",
    )


def check_minimum_size(content: str, min_lines: int) -> CheckResult:
    """Check that the artifact exceeds a minimum line count."""
    line_count = len(content.splitlines())
    if line_count >= min_lines:
        return CheckResult(
            name="minimum_size",
            passed=True,
            message=f"Artifact has {line_count} lines (minimum: {min_lines}).",
        )
    return CheckResult(
        name="minimum_size",
        passed=False,
        message=f"Artifact has only {line_count} lines (minimum: {min_lines}). "
        "Artifact may be incomplete.",
    )


# ── Aggregate runners ─────────────────────────────────────────────────


def check_finding_coverage(
    response_path: Path,
    review_path: Path | None = None,
) -> CheckResult:
    """Optional check: verify response addresses all review findings.

    If review_path is None, attempts to locate the previous round's review
    based on the response filename pattern. Returns a passing result if
    no review is found (graceful degradation).
    """
    if review_path is None:
        # Infer review path from response path
        # response: *_coder_response_round{N}.md → review: *_code_review_round{N}.md
        name = response_path.name
        review_name = name.replace("coder_response", "code_review")
        if review_name != name:
            candidate = response_path.parent / review_name
            if candidate.is_file():
                review_path = candidate

    if review_path is None or not review_path.is_file():
        return CheckResult(
            name="finding_coverage",
            passed=True,
            message="No review artifact found; skipping finding coverage check.",
        )

    try:
        from evolution.tools.finding_diff import validate
        result = validate(review_path, response_path)
        if result.passed:
            return CheckResult(
                name="finding_coverage",
                passed=True,
                message=f"All findings addressed: {result.summary}",
            )
        dropped = ", ".join(result.silently_dropped)
        return CheckResult(
            name="finding_coverage",
            passed=False,
            message=f"Silently dropped findings: {dropped}. {result.summary}",
        )
    except Exception as exc:
        return CheckResult(
            name="finding_coverage",
            passed=True,
            message=f"Finding coverage check skipped: {exc}",
        )


def run_code_preflight(
    artifact_path: Path,
    *,
    check_findings: bool = False,
    response_path: Path | None = None,
    review_path: Path | None = None,
) -> PreflightResult:
    """Run all code-mode preflight checks on an artifact.

    Args:
        artifact_path: Path to the code_complete artifact.
        check_findings: If True, also check finding coverage on the
            coder response (optional, not enabled by default).
        response_path: Path to the coder_response artifact for finding
            checks.  If None, falls back to *artifact_path*.
        review_path: Path to the review artifact for finding checks.
    """
    checks: list[CheckResult] = []

    exists = check_artifact_exists(artifact_path)
    checks.append(exists)
    if not exists.passed:
        return PreflightResult(passed=False, checks=checks)

    content = artifact_path.read_text()
    checks.append(check_code_file_headings(content))
    checks.append(check_code_diff_fences(content))
    checks.append(check_code_test_lines(content))
    checks.append(check_minimum_size(content, min_lines=50))

    if check_findings:
        checks.append(check_finding_coverage(
            response_path or artifact_path,
            review_path,
        ))

    passed = all(c.passed for c in checks)
    return PreflightResult(passed=passed, checks=checks)


def run_plan_preflight(artifact_path: Path) -> PreflightResult:
    """Run plan-mode preflight checks (exists + minimum size)."""
    checks: list[CheckResult] = []

    exists = check_artifact_exists(artifact_path)
    checks.append(exists)
    if not exists.passed:
        return PreflightResult(passed=False, checks=checks)

    content = artifact_path.read_text()
    checks.append(check_minimum_size(content, min_lines=20))

    passed = all(c.passed for c in checks)
    return PreflightResult(passed=passed, checks=checks)
