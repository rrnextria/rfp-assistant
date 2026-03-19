"""Tests for orchestrator_v3.postmortem — scanning, metrics, and report generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator_v3.config import OrchestratorSettings
from orchestrator_v3.postmortem import (
    ArtifactScan,
    CampaignMetrics,
    CampaignScanResult,
    RoundDetail,
    TaskMetrics,
    _parse_filename,
    calculate_metrics,
    generate_report,
    scan_campaign_artifacts,
    write_report,
)


# ── Helpers ───────────────────────────────────────────────────────────

ORCH_META_APPROVED = """\
<!-- ORCH_META
VERDICT: APPROVED
BLOCKER: 0
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 5
-->

# Review — approved
"""

ORCH_META_FIXES = """\
<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 1
MAJOR: 2
MINOR: 1
DECISIONS: 0
VERIFIED: 3
-->

# Review — fixes required
"""

ORCH_META_FIXES_MINOR = """\
<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 0
MAJOR: 0
MINOR: 2
-->

# Review — minor fixes
"""


def _make_settings(tmp_path):
    (tmp_path / "reviews").mkdir(exist_ok=True)
    (tmp_path / "active_plans").mkdir(exist_ok=True)
    return OrchestratorSettings(repo_root=tmp_path)


# ── Task 1: Filename parsing ─────────────────────────────────────────


class TestParseFilename:
    """1.3: Filename regex parsing for all observed patterns."""

    def test_code_mode_per_task(self):
        result = _parse_filename(
            "myslug", "myslug_phase_0_task_1_code_review_round1.md"
        )
        assert result == {
            "phase": 0, "task": 1, "label": None, "round": 1, "mode": "code",
        }

    def test_code_mode_higher_numbers(self):
        result = _parse_filename(
            "fp8", "fp8_phase_2_task_15_code_review_round3.md"
        )
        assert result == {
            "phase": 2, "task": 15, "label": None, "round": 3, "mode": "code",
        }

    def test_plan_mode_phase_stage(self):
        result = _parse_filename(
            "bf16_grad_compress",
            "bf16_grad_compress_phase_0_implementation_review_round1.md",
        )
        assert result is not None
        assert result["mode"] == "plan"
        assert result["phase"] == 0
        assert result["label"] == "phase_0_implementation"
        assert result["round"] == 1

    def test_plan_mode_master(self):
        result = _parse_filename(
            "bf16_grad_compress",
            "bf16_grad_compress_bf16_grad_compress_master_plan_review_round2.md",
        )
        assert result is not None
        assert result["mode"] == "plan"
        assert result["label"] == "bf16_grad_compress_master_plan"
        assert result["round"] == 2

    def test_plan_mode_master_slug_override(self):
        """B2 regression: master plan scan works when --slug overrides artifact slug."""
        result = _parse_filename(
            "triton_fused_moe_v3",
            "triton_fused_moe_v3_triton_fused_moe_master_plan_review_round1.md",
        )
        assert result is not None
        assert result["mode"] == "plan"
        assert result["label"] == "triton_fused_moe_master_plan"
        assert result["round"] == 1

    def test_plan_mode_label_fallback(self):
        result = _parse_filename(
            "myslug", "myslug_some_stage_review_round1.md"
        )
        assert result is not None
        assert result["mode"] == "plan"
        assert result["label"] == "some_stage"

    def test_wrong_slug_returns_none(self):
        result = _parse_filename(
            "myslug", "otherslug_phase_0_task_1_code_review_round1.md"
        )
        assert result is None

    def test_non_matching_returns_none(self):
        result = _parse_filename("myslug", "unrelated_file.md")
        assert result is None


# ── Task 1: Artifact scanning ────────────────────────────────────────


class TestScanCampaignArtifacts:
    """1.1-1.4: Scanner finds artifacts and extracts ORCH_META data."""

    def test_scan_three_artifacts(self, tmp_path):
        """1.5: 3 mock files with ORCH_META, verify all found with correct data."""
        settings = _make_settings(tmp_path)
        reviews = tmp_path / "reviews"

        # Create 3 review artifacts
        (reviews / "test_phase_0_task_1_code_review_round1.md").write_text(
            ORCH_META_FIXES
        )
        (reviews / "test_phase_0_task_1_code_review_round2.md").write_text(
            ORCH_META_APPROVED
        )
        (reviews / "test_phase_0_task_2_code_review_round1.md").write_text(
            ORCH_META_APPROVED
        )

        result = scan_campaign_artifacts("test", settings)

        assert result.slug == "test"
        assert len(result.artifacts) == 3

        # First artifact: fixes required
        a1 = result.artifacts[0]
        assert a1.phase == 0
        assert a1.task == 1
        assert a1.round == 1
        assert a1.mode == "code"
        assert a1.verdict == "FIXES_REQUIRED"
        assert a1.blocker == 1
        assert a1.major == 2

        # Second: approved
        a2 = result.artifacts[1]
        assert a2.round == 2
        assert a2.verdict == "APPROVED"

        # Third: different task, approved
        a3 = result.artifacts[2]
        assert a3.task == 2
        assert a3.verdict == "APPROVED"

    def test_scan_no_orch_meta(self, tmp_path):
        """1.6: Files without ORCH_META are handled gracefully."""
        settings = _make_settings(tmp_path)
        reviews = tmp_path / "reviews"

        (reviews / "test_phase_0_task_1_code_review_round1.md").write_text(
            "# Review\n\nSome review text without ORCH_META.\n"
        )

        result = scan_campaign_artifacts("test", settings)

        assert len(result.artifacts) == 1
        a = result.artifacts[0]
        assert a.verdict is None
        assert a.blocker == 0
        assert a.major == 0

    def test_scan_empty_dir(self, tmp_path):
        """No artifacts found for slug."""
        settings = _make_settings(tmp_path)
        result = scan_campaign_artifacts("nonexistent", settings)
        assert len(result.artifacts) == 0

    def test_scan_ignores_other_slugs(self, tmp_path):
        """Scanner only picks up files for the given slug."""
        settings = _make_settings(tmp_path)
        reviews = tmp_path / "reviews"

        (reviews / "test_phase_0_task_1_code_review_round1.md").write_text(
            ORCH_META_APPROVED
        )
        (reviews / "other_phase_0_task_1_code_review_round1.md").write_text(
            ORCH_META_APPROVED
        )

        result = scan_campaign_artifacts("test", settings)
        assert len(result.artifacts) == 1

    def test_scan_plan_and_code_mixed(self, tmp_path):
        """Scanner handles mixed code and plan artifacts."""
        settings = _make_settings(tmp_path)
        reviews = tmp_path / "reviews"

        (reviews / "myslug_phase_0_task_1_code_review_round1.md").write_text(
            ORCH_META_APPROVED
        )
        (reviews / "myslug_phase_0_implementation_review_round1.md").write_text(
            ORCH_META_FIXES
        )
        (reviews / "myslug_myslug_master_plan_review_round1.md").write_text(
            ORCH_META_APPROVED
        )

        result = scan_campaign_artifacts("myslug", settings)
        assert len(result.artifacts) == 3
        modes = {a.mode for a in result.artifacts}
        assert modes == {"code", "plan"}


# ── Task 2: Metrics calculation ──────────────────────────────────────


class TestCalculateMetrics:
    """2.1-2.5: Metrics calculation from scan results."""

    def _make_scan(self, slug, artifacts):
        return CampaignScanResult(slug=slug, artifacts=artifacts)

    def _code_art(self, phase, task, rnd, verdict, blocker=0, major=0, minor=0, verified=0):
        return ArtifactScan(
            path=Path(f"r_p{phase}_t{task}_r{rnd}.md"),
            phase=phase, task=task, label=None,
            round=rnd, mode="code",
            verdict=verdict, blocker=blocker, major=major, minor=minor,
            verified=verified,
        )

    def test_three_tasks_varying_rounds(self):
        """2.5: 3 tasks with 1, 2, 3 rounds to approval."""
        scan = self._make_scan("test", [
            # Task 1: approved R1
            self._code_art(0, 1, 1, "APPROVED"),
            # Task 2: fixes R1, approved R2
            self._code_art(0, 2, 1, "FIXES_REQUIRED", blocker=1),
            self._code_art(0, 2, 2, "APPROVED"),
            # Task 3: fixes R1, fixes R2, approved R3
            self._code_art(0, 3, 1, "FIXES_REQUIRED", major=1),
            self._code_art(0, 3, 2, "FIXES_REQUIRED", minor=2),
            self._code_art(0, 3, 3, "APPROVED"),
        ])

        m = calculate_metrics(scan)

        assert m.total_tasks == 3
        assert m.total_rounds == 6
        assert m.first_round_approvals == 1
        assert m.first_round_approval_rate == pytest.approx(1 / 3)
        assert m.avg_rounds_to_approval == pytest.approx(2.0)  # (1+2+3)/3
        assert m.total_blockers == 1
        assert m.total_majors == 1
        assert m.total_minors == 2
        # finding_resolution_rate: total findings = 1+1+2 = 4
        # verified in final rounds: task1 R1 verified=0, task2 R2 verified=0, task3 R3 verified=0
        # (using default verified=0 in _code_art)
        assert m.finding_resolution_rate == pytest.approx(0.0)

        # Per-task detail
        assert len(m.tasks_detail) == 3
        assert m.tasks_detail[0].rounds_to_approval == 1
        assert m.tasks_detail[1].rounds_to_approval == 2
        assert m.tasks_detail[2].rounds_to_approval == 3

    def test_empty_scan(self):
        """Empty scan produces zero metrics."""
        m = calculate_metrics(CampaignScanResult(slug="empty"))
        assert m.total_tasks == 0
        assert m.total_rounds == 0
        assert m.first_round_approval_rate == 0.0

    def test_task_not_yet_approved(self):
        """2.4: Task still in progress (no approval)."""
        scan = self._make_scan("test", [
            self._code_art(0, 1, 1, "FIXES_REQUIRED", blocker=1),
        ])

        m = calculate_metrics(scan)

        assert m.total_tasks == 1
        assert m.tasks_detail[0].rounds_to_approval is None
        assert m.first_round_approvals == 0
        assert m.avg_rounds_to_approval == 0.0  # no approved tasks

    def test_finding_resolution_rate(self):
        """finding_resolution_rate = verified in final rounds / total findings."""
        scan = self._make_scan("test", [
            # Task 1: 1 blocker in R1, 1 verified in R2 (approved)
            self._code_art(0, 1, 1, "FIXES_REQUIRED", blocker=1),
            self._code_art(0, 1, 2, "APPROVED", verified=1),
            # Task 2: 2 majors in R1, 3 verified in R2 (approved)
            self._code_art(0, 2, 1, "FIXES_REQUIRED", major=2),
            self._code_art(0, 2, 2, "APPROVED", verified=3),
        ])

        m = calculate_metrics(scan)

        # Total findings: 1 + 2 = 3, verified in final rounds: 1 + 3 = 4
        # Rate = min(1.0, 4/3) = 1.0 (capped at 1.0)
        assert m.finding_resolution_rate == pytest.approx(1.0)

    def test_mode_breakdown(self):
        """avg_rounds_by_mode separates code and plan."""
        scan = self._make_scan("test", [
            self._code_art(0, 1, 1, "APPROVED"),
            ArtifactScan(
                path=Path("r.md"), phase=None, task=None,
                label="master_plan", round=1, mode="plan",
                verdict="FIXES_REQUIRED",
            ),
            ArtifactScan(
                path=Path("r2.md"), phase=None, task=None,
                label="master_plan", round=2, mode="plan",
                verdict="APPROVED",
            ),
        ])

        m = calculate_metrics(scan)

        assert m.avg_rounds_by_mode["code"] == pytest.approx(1.0)
        assert m.avg_rounds_by_mode["plan"] == pytest.approx(2.0)


# ── Task 2.6: Integration test with real bf16_grad_compress artifacts ─

REPO_ROOT = Path(__file__).resolve().parents[5]


class TestMetricsIntegration:
    """2.6: Validate metrics against real campaign artifacts."""

    def test_bf16_grad_compress_metrics(self):
        """Scan bf16_grad_compress and verify known round counts."""
        reviews_dir = REPO_ROOT / "reviews"
        if not (reviews_dir / "bf16_grad_compress_phase_0_task_1_code_review_round1.md").exists():
            pytest.skip("bf16_grad_compress artifacts not found")

        settings = OrchestratorSettings(repo_root=REPO_ROOT)
        scan = scan_campaign_artifacts("bf16_grad_compress", settings)

        assert len(scan.artifacts) > 0, "Should find bf16_grad_compress artifacts"

        m = calculate_metrics(scan)

        # Known facts about bf16_grad_compress campaign:
        # - Phase 0 has 4 code tasks
        # - Task 4 took 3 rounds (check round count)
        # - Tasks 1-3 took 1 round each
        code_tasks = [t for t in m.tasks_detail if t.mode == "code"]
        assert len(code_tasks) >= 4

        # Task 4 (phase 0) took 3 rounds
        t4 = [t for t in code_tasks if t.phase == 0 and t.task == 4]
        assert len(t4) == 1
        assert t4[0].rounds_to_approval == 3

        # Tasks 1-3 took 1 round each
        for task_num in [1, 2, 3]:
            t = [t for t in code_tasks if t.phase == 0 and t.task == task_num]
            assert len(t) == 1
            assert t[0].rounds_to_approval == 1

        # B1 fix: Verify aggregate metrics (total_rounds, first_round_approval_rate)
        # 13 artifacts total: 4 code (1+1+1+3) + 9 plan (2+2+3)
        assert m.total_rounds == 13
        # 7 tasks total (4 code + 3 plan), 3 first-round approvals (code tasks 1-3)
        assert m.total_tasks == 7
        assert m.first_round_approvals == 3
        assert m.first_round_approval_rate == pytest.approx(3 / 7)


# ── Task 3: Report generation ────────────────────────────────────────


class TestGenerateReport:
    """3.1-3.5: Report generation from metrics."""

    def _sample_metrics(self):
        return CampaignMetrics(
            slug="test",
            total_tasks=2,
            total_rounds=3,
            first_round_approvals=1,
            first_round_approval_rate=0.5,
            avg_rounds_to_approval=1.5,
            total_blockers=1,
            total_majors=0,
            total_minors=2,
            avg_rounds_by_mode={"code": 1.5},
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
                        RoundDetail(round=1, verdict="FIXES_REQUIRED", blocker=1),
                        RoundDetail(round=2, verdict="APPROVED", verified=5),
                    ],
                ),
            ],
        )

    def test_report_has_expected_sections(self):
        """3.4: Report contains all required markdown sections."""
        report = generate_report(self._sample_metrics(), reflection="Some reflection text.")
        assert "# Campaign Postmortem: test" in report
        assert "## Campaign Summary" in report
        assert "## Per-Task Breakdown" in report
        assert "## Metrics" in report
        assert "## Evolutionary Reflection" in report
        assert "Some reflection text." in report

    def test_report_without_reflection(self):
        """3.5: No Evolutionary Reflection section when reflection=None."""
        report = generate_report(self._sample_metrics(), reflection=None)
        assert "## Campaign Summary" in report
        assert "## Evolutionary Reflection" not in report

    def test_report_metrics_values(self):
        """Report includes correct metric values."""
        report = generate_report(self._sample_metrics())
        assert "Total tasks/stages:** 2" in report
        assert "Total review rounds:** 3" in report
        assert "1/2" in report  # first-round approval rate
        assert "50%" in report
        assert "Finding resolution rate" in report

    def test_report_table_rows(self):
        """Per-task table has correct rows."""
        report = generate_report(self._sample_metrics())
        # Task 1: approved R1
        assert "R1" in report
        # Task 2: approved R2
        assert "R2" in report
        assert "FIXES_REQUIRED" in report


class TestWriteReport:
    """3.3: write_report writes to correct path."""

    def test_write_creates_file(self, tmp_path):
        settings = _make_settings(tmp_path)
        path = write_report("test", "# Report\n", settings)
        assert path.exists()
        assert path.name == "test_postmortem.md"
        assert path.read_text() == "# Report\n"
