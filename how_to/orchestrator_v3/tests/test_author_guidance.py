"""Tests for author guidance checklists in the waiting banner.

Phase 1, Task 1: Verify that print_waiting_banner() outputs
mode-specific guidance checklists for code and plan modes.
"""

from __future__ import annotations


def _capture_waiting_banner(**kwargs) -> str:
    """Call print_waiting_banner and capture its stdout."""
    import io
    import contextlib

    from orchestrator_v3.display import print_waiting_banner

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_waiting_banner(**kwargs)
    return buf.getvalue()


class TestCodeModeGuidance:
    """Gate 1: Code-mode waiting banner prints author guidance checklist."""

    def test_code_guidance_contains_file_heading_reminder(self):
        output = _capture_waiting_banner(
            mode="code", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "File:" in output

    def test_code_guidance_contains_diff_fence_reminder(self):
        output = _capture_waiting_banner(
            mode="code", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "~~~diff" in output

    def test_code_guidance_contains_test_line_reminder(self):
        output = _capture_waiting_banner(
            mode="code", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "Test:" in output

    def test_code_guidance_contains_hash_reminder(self):
        output = _capture_waiting_banner(
            mode="code", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "SHA-256" in output or "hash" in output.lower()

    def test_code_guidance_contains_summary_reminder(self):
        output = _capture_waiting_banner(
            mode="code", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "Summary" in output or "summary" in output

    def test_code_guidance_contains_checklist_header(self):
        output = _capture_waiting_banner(
            mode="code", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "Author Checklist" in output


class TestPlanModeGuidance:
    """Gate 2: Plan-mode waiting banner prints author guidance checklist."""

    def test_plan_guidance_contains_finding_reminder(self):
        output = _capture_waiting_banner(
            mode="plan", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "finding" in output.lower()

    def test_plan_guidance_contains_subtask_reminder(self):
        output = _capture_waiting_banner(
            mode="plan", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "subtask" in output.lower() or "Subtask" in output

    def test_plan_guidance_contains_acceptance_reminder(self):
        output = _capture_waiting_banner(
            mode="plan", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "acceptance" in output.lower() or "Acceptance" in output

    def test_plan_guidance_contains_section_reminder(self):
        output = _capture_waiting_banner(
            mode="plan", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "section" in output.lower() or "Section" in output

    def test_plan_guidance_contains_checklist_header(self):
        output = _capture_waiting_banner(
            mode="plan", round=1,
            review_file="review.md", response_file="response.md",
        )
        assert "Author Checklist" in output


class TestGuidanceNoColor:
    """Verify guidance works when NO_COLOR is set."""

    def test_code_guidance_no_color(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        # Re-import to pick up NO_COLOR
        import importlib
        import orchestrator_v3.display as disp
        importlib.reload(disp)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                disp.print_waiting_banner(
                    mode="code", round=1,
                    review_file="r.md", response_file="resp.md",
                )
            output = buf.getvalue()
            assert "File:" in output
            assert "~~~diff" in output
            # No ANSI escape codes
            assert "\033[" not in output
        finally:
            monkeypatch.delenv("NO_COLOR", raising=False)
            importlib.reload(disp)

    def test_plan_guidance_no_color(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        import importlib
        import orchestrator_v3.display as disp
        importlib.reload(disp)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                disp.print_waiting_banner(
                    mode="plan", round=1,
                    review_file="r.md", response_file="resp.md",
                )
            output = buf.getvalue()
            assert "finding" in output.lower()
            assert "Subtask" in output
            assert "\033[" not in output
        finally:
            monkeypatch.delenv("NO_COLOR", raising=False)
            importlib.reload(disp)
