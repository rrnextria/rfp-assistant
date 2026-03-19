"""Unit and end-to-end tests for orchestrator_v3.approval module."""

import pytest

from orchestrator_v3.approval import Verdict, check_approved, parse_orch_meta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_md(tmp_path, name, content):
    """Write a .md file in tmp_path and return its Path."""
    p = tmp_path / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Task 3: Unit Tests (9 cases)
# ---------------------------------------------------------------------------

class TestParseOrchMeta:
    """Tests 3.1 – 3.9 from the Phase 1 plan."""

    def test_valid_approved_review(self, tmp_path):
        """3.1: Valid APPROVED review with all counts 0."""
        f = _write_md(tmp_path, "approved.md", (
            "<!-- ORCH_META\n"
            "VERDICT: APPROVED\n"
            "BLOCKER: 0\n"
            "MAJOR: 0\n"
            "MINOR: 0\n"
            "DECISIONS: 0\n"
            "VERIFIED: 9\n"
            "-->\n"
            "\n"
            "# Review Round 1\n"
        ))
        result = parse_orch_meta(f)
        assert result is not None
        assert result.verdict == Verdict.APPROVED
        assert result.blocker == 0
        assert result.major == 0
        assert result.minor == 0
        assert result.decisions == 0
        assert result.verified == 9
        assert check_approved(f) is True

    def test_valid_fixes_required_review(self, tmp_path):
        """3.2: Valid FIXES_REQUIRED review with non-zero counts."""
        f = _write_md(tmp_path, "fixes.md", (
            "<!-- ORCH_META\n"
            "VERDICT: FIXES_REQUIRED\n"
            "BLOCKER: 2\n"
            "MAJOR: 1\n"
            "MINOR: 3\n"
            "DECISIONS: 0\n"
            "VERIFIED: 5\n"
            "-->\n"
        ))
        result = parse_orch_meta(f)
        assert result is not None
        assert result.verdict == Verdict.FIXES_REQUIRED
        assert result.blocker == 2
        assert result.major == 1
        assert result.minor == 3
        assert result.decisions == 0
        assert result.verified == 5
        assert check_approved(f) is False

    def test_missing_orch_meta_block(self, tmp_path):
        """3.3: File exists but no ORCH_META block → fail-closed."""
        f = _write_md(tmp_path, "no_meta.md", (
            "# Review Round 1\n"
            "\n"
            "Good work overall. Some minor issues.\n"
            "\n"
            "## Findings\n"
            "- B1: Fix the bug\n"
        ))
        assert parse_orch_meta(f) is None
        assert check_approved(f) is False

    def test_malformed_missing_verdict(self, tmp_path):
        """3.4: ORCH_META block present but VERDICT key missing."""
        f = _write_md(tmp_path, "no_verdict.md", (
            "<!-- ORCH_META\n"
            "BLOCKER: 0\n"
            "MAJOR: 0\n"
            "MINOR: 0\n"
            "DECISIONS: 0\n"
            "VERIFIED: 5\n"
            "-->\n"
        ))
        assert parse_orch_meta(f) is None
        assert check_approved(f) is False

    def test_approved_with_nonzero_blocker(self, tmp_path):
        """3.5: VERDICT=APPROVED but BLOCKER=1 → counts override verdict."""
        f = _write_md(tmp_path, "approved_blocker.md", (
            "<!-- ORCH_META\n"
            "VERDICT: APPROVED\n"
            "BLOCKER: 1\n"
            "MAJOR: 0\n"
            "MINOR: 0\n"
            "DECISIONS: 0\n"
            "VERIFIED: 8\n"
            "-->\n"
        ))
        result = parse_orch_meta(f)
        assert result is not None
        assert result.verdict == Verdict.APPROVED
        assert result.blocker == 1
        assert check_approved(f) is False

    def test_file_does_not_exist(self, tmp_path):
        """3.6: Non-existent file → None, no exception."""
        missing = tmp_path / "nonexistent.md"
        assert parse_orch_meta(missing) is None
        assert check_approved(missing) is False

    def test_extra_whitespace(self, tmp_path):
        """3.7: Extra whitespace around keys and values → handled."""
        f = _write_md(tmp_path, "whitespace.md", (
            "  <!-- ORCH_META  \n"
            "  VERDICT :  APPROVED  \n"
            "  BLOCKER :  0  \n"
            "  MAJOR :  0  \n"
            "  MINOR :  0  \n"
            "  DECISIONS :  0  \n"
            "  VERIFIED :  9  \n"
            "  -->  \n"
        ))
        result = parse_orch_meta(f)
        assert result is not None
        assert result.verdict == Verdict.APPROVED
        assert result.blocker == 0
        assert check_approved(f) is True

    def test_legacy_review_without_orch_meta(self, tmp_path):
        """3.8: v1-style approval text in prose → NOT approved."""
        f = _write_md(tmp_path, "legacy.md", (
            "# Review Round 3\n"
            "\n"
            "Approved -- no further rounds needed.\n"
            "\n"
            "All findings have been resolved.\n"
        ))
        assert parse_orch_meta(f) is None
        assert check_approved(f) is False

    def test_orch_meta_buried_past_line_50(self, tmp_path):
        """3.9: ORCH_META block starting past line 50 → not found."""
        preamble = "\n".join(f"Line {i}" for i in range(1, 56))
        content = (
            preamble + "\n"
            "<!-- ORCH_META\n"
            "VERDICT: APPROVED\n"
            "BLOCKER: 0\n"
            "MAJOR: 0\n"
            "MINOR: 0\n"
            "DECISIONS: 0\n"
            "VERIFIED: 5\n"
            "-->\n"
        )
        f = _write_md(tmp_path, "buried.md", content)
        assert parse_orch_meta(f) is None
        assert check_approved(f) is False


# ---------------------------------------------------------------------------
# Regression tests for Round 1 findings (B1, M1)
# ---------------------------------------------------------------------------

class TestRound1Regressions:
    """Regression tests for issues found during code review Round 1."""

    def test_truncated_block_missing_end_marker(self, tmp_path):
        """B1 regression: ORCH_META without closing --> must fail-closed."""
        f = _write_md(tmp_path, "truncated.md", (
            "<!-- ORCH_META\n"
            "VERDICT: APPROVED\n"
            "BLOCKER: 0\n"
            "MAJOR: 0\n"
            "MINOR: 0\n"
            "DECISIONS: 0\n"
            "VERIFIED: 9\n"
            "\n"
            "# Review body (no closing -->)\n"
        ))
        assert parse_orch_meta(f) is None
        assert check_approved(f) is False

    def test_truncated_block_body_spoofing_past_line_50(self, tmp_path):
        """B1 regression: Missing --> with spoofing body past line 50."""
        # Start marker at line 1, FIXES_REQUIRED at line 2, but no -->.
        # Body text past line 50 contains VERDICT: APPROVED (would spoof
        # if the parser didn't enforce the line 50 safety bound).
        header = (
            "<!-- ORCH_META\n"
            "VERDICT: FIXES_REQUIRED\n"
            "BLOCKER: 3\n"
        )
        # Pad to push past line 50
        padding = "".join(f"padding line {i}\n" for i in range(4, 52))
        spoofing_body = (
            "VERDICT: APPROVED\n"
            "BLOCKER: 0\n"
            "MAJOR: 0\n"
            "MINOR: 0\n"
            "DECISIONS: 0\n"
            "-->\n"
        )
        f = _write_md(tmp_path, "spoof_truncated.md",
                       header + padding + spoofing_body)
        # Must fail-closed: block opened but --> not found within 50 lines
        assert parse_orch_meta(f) is None
        assert check_approved(f) is False

    def test_approved_missing_count_keys(self, tmp_path):
        """M1 regression: APPROVED without count keys must fail-closed."""
        f = _write_md(tmp_path, "no_counts.md", (
            "<!-- ORCH_META\n"
            "VERDICT: APPROVED\n"
            "-->\n"
        ))
        assert parse_orch_meta(f) is None
        assert check_approved(f) is False

    def test_approved_partial_count_keys(self, tmp_path):
        """M1 regression: APPROVED with only BLOCKER (missing MAJOR/MINOR/DECISIONS)."""
        f = _write_md(tmp_path, "partial_counts.md", (
            "<!-- ORCH_META\n"
            "VERDICT: APPROVED\n"
            "BLOCKER: 0\n"
            "-->\n"
        ))
        assert parse_orch_meta(f) is None
        assert check_approved(f) is False

    def test_fixes_required_missing_counts_still_parses(self, tmp_path):
        """M1 contrast: FIXES_REQUIRED without counts is valid (defaults to 0)."""
        f = _write_md(tmp_path, "fixes_no_counts.md", (
            "<!-- ORCH_META\n"
            "VERDICT: FIXES_REQUIRED\n"
            "-->\n"
        ))
        result = parse_orch_meta(f)
        assert result is not None
        assert result.verdict == Verdict.FIXES_REQUIRED
        assert result.blocker == 0
        assert check_approved(f) is False


# ---------------------------------------------------------------------------
# Task 4: End-to-End Validation with Mock Artifacts (4 cases)
# ---------------------------------------------------------------------------

_APPROVED_REVIEW_MD = """\
<!-- ORCH_META
VERDICT: APPROVED
BLOCKER: 0
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 9
-->

# Code Review: orchestrator_v3 — Phase 0, Task 1 (Round 3)

**Plan:** orchestrator_v3
**Phase:** 0 (Foundation)
**Task:** 1 (All foundational modules)
**Round:** 3
**Reviewer:** GPT-5.2 (high)

---

## Summary

All findings from Round 2 have been resolved. The implementation is clean,
well-tested, and ready for production use.

## Verified Items

1. B1 (Round 1): Enum validation — VERIFIED ✓
2. M1 (Round 1): Artifact format — VERIFIED ✓
3. M2 (Round 1): Round-trip test — VERIFIED ✓
4. N1 (Round 1): Docstring wording — VERIFIED ✓
5. N2 (Round 1): Default factories — VERIFIED ✓
6. N3 (Round 1): Exception type — VERIFIED ✓
7. B1 (Round 2): save() return semantics — VERIFIED ✓
8. N1 (Round 2): Backup test content — VERIFIED ✓
9. N2 (Round 2): Unused import — VERIFIED ✓
"""

_FIXES_REQUIRED_REVIEW_MD = """\
<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 1
MAJOR: 2
MINOR: 1
DECISIONS: 0
VERIFIED: 6
-->

# Code Review: orchestrator_v3 — Phase 0, Task 1 (Round 1)

**Plan:** orchestrator_v3
**Phase:** 0 (Foundation)
**Round:** 1
**Reviewer:** GPT-5.2 (high)

---

## Findings

### B1) Enum types stored as plain str

The `OrchestratorState` model uses `mode: str` instead of `mode: Mode`.

### M1) Missing artifact format

Code-complete artifact lacks `File:` headings.

### M2) Incomplete round-trip test

Only 4 of 16 fields verified.

### N1) Minor docstring wording

"3 levels up" should be "4 parents up".
"""

_PROSE_SPOOFING_REVIEW_MD = """\
<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 3
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 2
-->

# Review Round 1

The reviewer should set VERDICT: APPROVED when all findings are resolved
and BLOCKER: 0 in the ORCH_META block. Currently there are outstanding
issues so VERDICT: FIXES_REQUIRED is the correct choice.

## Findings

### B1) Critical issue one
### B2) Critical issue two
### B3) Critical issue three
"""


class TestEndToEndMockArtifacts:
    """Tasks 4.1 – 4.4 from the Phase 1 plan."""

    def test_approved_review_artifact(self, tmp_path):
        """4.1: Realistic approved review with substantial markdown body."""
        f = _write_md(tmp_path, "review_approved.md", _APPROVED_REVIEW_MD)
        result = parse_orch_meta(f)
        assert result is not None
        assert result.verdict == Verdict.APPROVED
        assert result.blocker == 0
        assert result.verified == 9
        assert check_approved(f) is True

    def test_fixes_required_artifact(self, tmp_path):
        """4.2: Fixes-required review with finding sections below."""
        f = _write_md(tmp_path, "review_fixes.md", _FIXES_REQUIRED_REVIEW_MD)
        result = parse_orch_meta(f)
        assert result is not None
        assert result.verdict == Verdict.FIXES_REQUIRED
        assert result.blocker == 1
        assert result.major == 2
        assert result.minor == 1
        assert check_approved(f) is False

    def test_prose_does_not_spoof_orch_meta(self, tmp_path):
        """4.3: Prose contains 'VERDICT: APPROVED' but ORCH_META says FIXES_REQUIRED."""
        f = _write_md(tmp_path, "review_spoof.md", _PROSE_SPOOFING_REVIEW_MD)
        result = parse_orch_meta(f)
        assert result is not None
        assert result.verdict == Verdict.FIXES_REQUIRED
        assert result.blocker == 3
        assert check_approved(f) is False

    @pytest.mark.parametrize(
        "fixture,expected_approved",
        [
            (_APPROVED_REVIEW_MD, True),
            (_FIXES_REQUIRED_REVIEW_MD, False),
            (_PROSE_SPOOFING_REVIEW_MD, False),
        ],
        ids=["approved", "fixes_required", "prose_spoofing"],
    )
    def test_parametrized_pipeline(self, tmp_path, fixture, expected_approved):
        """4.4: Parametrized smoke test across all three fixtures."""
        f = _write_md(tmp_path, "review.md", fixture)
        assert check_approved(f) is expected_approved
