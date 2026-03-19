"""Tests for orchestrator_v3.reflection — prompt building and artifact selection."""

from __future__ import annotations

from orchestrator_v3.postmortem import (
    ArtifactScan,
    CampaignMetrics,
    CampaignScanResult,
    RoundDetail,
    TaskMetrics,
)
from orchestrator_v3.reflection import (
    build_reflection_prompt,
    run_reflection,
    select_failing_artifacts,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _sample_metrics():
    return CampaignMetrics(
        slug="test_campaign",
        total_tasks=3,
        total_rounds=6,
        first_round_approvals=1,
        first_round_approval_rate=1 / 3,
        avg_rounds_to_approval=2.0,
        total_blockers=2,
        total_majors=1,
        total_minors=3,
        tasks_detail=[
            TaskMetrics(
                phase=0, task=1, label=None, mode="code",
                rounds_to_approval=1,
                round_details=[
                    RoundDetail(round=1, verdict="APPROVED", verified=5),
                ],
            ),
            TaskMetrics(
                phase=0, task=2, label=None, mode="code",
                rounds_to_approval=2,
                round_details=[
                    RoundDetail(round=1, verdict="FIXES_REQUIRED", blocker=1, major=1),
                    RoundDetail(round=2, verdict="APPROVED", verified=6),
                ],
            ),
            TaskMetrics(
                phase=0, task=3, label=None, mode="code",
                rounds_to_approval=3,
                round_details=[
                    RoundDetail(round=1, verdict="FIXES_REQUIRED", blocker=1),
                    RoundDetail(round=2, verdict="FIXES_REQUIRED", minor=3),
                    RoundDetail(round=3, verdict="APPROVED", verified=7),
                ],
            ),
        ],
    )


# ── Task 4.5: Reflection prompt contains all instruction sections ────


class TestBuildReflectionPrompt:
    """4.5: Prompt output contains all 5 instruction sections."""

    def test_contains_pattern_identification(self):
        prompt = build_reflection_prompt(_sample_metrics(), {})
        assert "Pattern Identification" in prompt

    def test_contains_root_cause_classification(self):
        prompt = build_reflection_prompt(_sample_metrics(), {})
        assert "Root Cause Classification" in prompt

    def test_contains_guidance_recommendations(self):
        prompt = build_reflection_prompt(_sample_metrics(), {})
        assert "Guidance Recommendations" in prompt

    def test_contains_preflight_recommendations(self):
        prompt = build_reflection_prompt(_sample_metrics(), {})
        assert "Preflight Recommendations" in prompt

    def test_contains_reviewer_consistency(self):
        prompt = build_reflection_prompt(_sample_metrics(), {})
        assert "Reviewer Consistency" in prompt

    def test_contains_metrics_summary(self):
        prompt = build_reflection_prompt(_sample_metrics(), {})
        assert "test_campaign" in prompt
        assert "Total tasks: 3" in prompt
        assert "Total rounds: 6" in prompt

    def test_contains_artifact_contents(self):
        artifacts = {"review_round1.md": "# Review\n\nB1: Some blocker"}
        prompt = build_reflection_prompt(_sample_metrics(), artifacts)
        assert "review_round1.md" in prompt
        assert "B1: Some blocker" in prompt

    def test_no_artifacts_section_when_empty(self):
        prompt = build_reflection_prompt(_sample_metrics(), {})
        assert "Review Artifacts (Non-Approved Rounds)" not in prompt


# ── Task 4.6: select_failing_artifacts ────────────────────────────────


class TestSelectFailingArtifacts:
    """4.6: Selects only non-approved artifacts."""

    def test_selects_only_failing(self, tmp_path):
        """3 artifacts (2 failing, 1 approved) → returns only the 2 failing."""
        (tmp_path / "fixes1.md").write_text("Fixes round 1")
        (tmp_path / "fixes2.md").write_text("Fixes round 2")
        (tmp_path / "approved.md").write_text("Approved round 3")

        scan = CampaignScanResult(
            slug="test",
            artifacts=[
                ArtifactScan(
                    path=tmp_path / "fixes1.md", phase=0, task=1, label=None,
                    round=1, mode="code", verdict="FIXES_REQUIRED", blocker=1,
                ),
                ArtifactScan(
                    path=tmp_path / "fixes2.md", phase=0, task=1, label=None,
                    round=2, mode="code", verdict="FIXES_REQUIRED", minor=2,
                ),
                ArtifactScan(
                    path=tmp_path / "approved.md", phase=0, task=1, label=None,
                    round=3, mode="code", verdict="APPROVED",
                ),
            ],
        )

        result = select_failing_artifacts(scan)

        assert len(result) == 2
        assert "fixes1.md" in result
        assert "fixes2.md" in result
        assert "approved.md" not in result
        assert result["fixes1.md"] == "Fixes round 1"

    def test_no_orch_meta_included(self, tmp_path):
        """Artifacts with verdict=None (no ORCH_META) are included."""
        (tmp_path / "old.md").write_text("Old format review")

        scan = CampaignScanResult(
            slug="test",
            artifacts=[
                ArtifactScan(
                    path=tmp_path / "old.md", phase=0, task=1, label=None,
                    round=1, mode="code", verdict=None,
                ),
            ],
        )

        result = select_failing_artifacts(scan)
        assert len(result) == 1

    def test_all_approved_returns_empty(self, tmp_path):
        """All approved artifacts → empty dict."""
        (tmp_path / "ok.md").write_text("All good")

        scan = CampaignScanResult(
            slug="test",
            artifacts=[
                ArtifactScan(
                    path=tmp_path / "ok.md", phase=0, task=1, label=None,
                    round=1, mode="code", verdict="APPROVED",
                ),
            ],
        )

        result = select_failing_artifacts(scan)
        assert len(result) == 0


# ── Task 4.3: run_reflection ─────────────────────────────────────────


class TestRunReflection:
    """4.3: run_reflection uses reviewer backend."""

    def test_success_returns_content(self, tmp_path):
        """Successful reflection returns the file content."""
        output_path = tmp_path / "reflection.md"

        class StubReviewer:
            def run_review(self, prompt, review_file, log_file):
                review_file.write_text("# Reflection\n\nSome insights.")
                return True

        result = run_reflection("prompt", output_path, StubReviewer())
        assert result is not None
        assert "Some insights" in result

    def test_failure_returns_none(self, tmp_path):
        """Failed review returns None."""
        output_path = tmp_path / "reflection.md"

        class FailReviewer:
            def run_review(self, prompt, review_file, log_file):
                return False

        result = run_reflection("prompt", output_path, FailReviewer())
        assert result is None

    def test_log_fallback_when_review_file_not_created(self, tmp_path):
        """B1 regression: extract reflection from log when .md file not created."""
        output_path = tmp_path / "reflection.md"

        class LogOnlyReviewer:
            def run_review(self, prompt, review_file, log_file):
                # Simulates Codex writing to stdout (captured in log) but NOT to review_file
                log_file.write_text(
                    "OpenAI Codex v0.98.0\n"
                    "--------\n"
                    "user\n"
                    "## 1. Pattern Identification\n"  # prompt echo
                    "Identify recurring patterns...\n"
                    "tokens used\n"
                    "6,956\n"
                    "## 1. Pattern Identification\n"  # actual output
                    "\n"
                    "Recurring issues found.\n"
                    "\n"
                    "## 2. Root Cause Classification\n"
                    "\n"
                    "Format issues: 2\n"
                )
                return True

        result = run_reflection("prompt", output_path, LogOnlyReviewer())
        assert result is not None
        assert "## 1. Pattern Identification" in result
        assert "Recurring issues found" in result
        assert "## 2. Root Cause Classification" in result
        # Should not include the Codex header
        assert "OpenAI Codex" not in result
