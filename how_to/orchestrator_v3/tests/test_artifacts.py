"""Unit tests for orchestrator_v3.artifacts module."""

import pytest

from orchestrator_v3.artifacts import ArtifactResolver
from orchestrator_v3.config import Mode, PlanType


class TestCodeModePaths:
    def test_code_review_path(self, tmp_settings):
        r = ArtifactResolver(
            slug="fp8_training", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        path = r.review_path(1)
        assert path.name == "fp8_training_phase_0_task_1_code_review_round1.md"
        assert path.parent == tmp_settings.reviews_dir

    def test_code_response_path(self, tmp_settings):
        r = ArtifactResolver(
            slug="fp8_training", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        path = r.response_path(1)
        assert path.name == "fp8_training_phase_0_task_1_coder_response_round1.md"

    def test_code_complete_path(self, tmp_settings):
        r = ArtifactResolver(
            slug="fp8_training", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        path = r.complete_path(1)
        assert path.name == "fp8_training_phase_0_task_1_code_complete_round1.md"


class TestPlanModePaths:
    def test_plan_review_path_simple(self, tmp_settings):
        r = ArtifactResolver(
            slug="my_plan", mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings, stage_label=None,
        )
        path = r.review_path(2)
        assert path.name == "my_plan_plan_review_round2.md"

    def test_plan_review_path_stage(self, tmp_settings):
        r = ArtifactResolver(
            slug="fp8_training", mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings, stage_label="phase_0_foundation",
        )
        path = r.review_path(1)
        assert path.name == "fp8_training_phase_0_foundation_review_round1.md"

    def test_plan_update_path_simple(self, tmp_settings):
        r = ArtifactResolver(
            slug="my_plan", mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings, stage_label=None,
        )
        path = r.response_path(3)
        assert path.name == "my_plan_plan_update_round3.md"

    def test_plan_update_path_stage(self, tmp_settings):
        r = ArtifactResolver(
            slug="fp8_training", mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings, stage_label="master_plan",
        )
        path = r.response_path(1)
        assert path.name == "fp8_training_master_plan_update_round1.md"

    def test_complete_path_raises_for_plan_mode(self, tmp_settings):
        r = ArtifactResolver(
            slug="test", mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        with pytest.raises(ValueError, match="code mode"):
            r.complete_path(1)


class TestDetectPlanType:
    def test_detect_complex(self, tmp_settings, complex_plan_dir):
        slug, _ = complex_plan_dir
        r = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        assert r.detect_plan_type() == PlanType.COMPLEX

    def test_detect_simple(self, tmp_settings, simple_plan_file):
        slug, _ = simple_plan_file
        r = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        assert r.detect_plan_type() == PlanType.SIMPLE

    def test_detect_empty_phases_dir(self, tmp_settings):
        slug = "empty_phases"
        phases_dir = tmp_settings.active_plans_dir / slug / "phases"
        phases_dir.mkdir(parents=True)
        r = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        assert r.detect_plan_type() == PlanType.COMPLEX


class TestFindPlanFile:
    def test_find_complex(self, tmp_settings, complex_plan_dir):
        slug, plan_dir = complex_plan_dir
        r = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        result = r.find_plan_file()
        assert result.name == f"{slug}_master_plan.md"
        assert result.exists()

    def test_find_simple(self, tmp_settings, simple_plan_file):
        slug, plan_file = simple_plan_file
        r = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        result = r.find_plan_file()
        assert result == plan_file

    def test_find_simple_alt_naming(self, tmp_settings):
        slug = "alt_slug"
        plan_dir = tmp_settings.active_plans_dir / slug
        plan_dir.mkdir()
        plan_file = plan_dir / f"{slug}_plan.md"
        plan_file.write_text("# Alt Plan\n")
        r = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        result = r.find_plan_file()
        assert result == plan_file

    def test_find_not_found(self, tmp_settings):
        r = ArtifactResolver(
            slug="nonexistent", mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        with pytest.raises(FileNotFoundError):
            r.find_plan_file()


class TestGetReviewStages:
    def test_complex_plan_stages(self, tmp_settings, complex_plan_dir):
        slug, _ = complex_plan_dir
        r = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        stages = r.get_review_stages()
        assert len(stages) == 2  # phase_0 + master
        assert "phase_0" in stages[0].name
        assert "master_plan" in stages[1].name

    def test_simple_plan_stages(self, tmp_settings, simple_plan_file):
        slug, plan_file = simple_plan_file
        r = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        stages = r.get_review_stages()
        assert len(stages) == 1
        assert stages[0] == plan_file

    def test_numeric_sort_order(self, tmp_settings):
        """Verify phase_10 sorts after phase_2, not before."""
        slug = "sort_test"
        phases_dir = tmp_settings.active_plans_dir / slug / "phases"
        phases_dir.mkdir(parents=True)
        master = tmp_settings.active_plans_dir / slug / f"{slug}_master_plan.md"
        master.write_text("# Master\n")

        for i in [2, 10, 1, 0]:
            (phases_dir / f"phase_{i}_test.md").write_text(f"# Phase {i}\n")

        r = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings,
        )
        stages = r.get_review_stages()
        phase_names = [s.name for s in stages[:-1]]  # exclude master
        assert phase_names == [
            "phase_0_test.md",
            "phase_1_test.md",
            "phase_2_test.md",
            "phase_10_test.md",
        ]


class TestScanExistingRounds:
    def test_scan_no_artifacts(self, tmp_settings):
        r = ArtifactResolver(
            slug="test", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        assert r.scan_existing_rounds() == (0, 0)

    def test_scan_review_only(self, tmp_settings):
        r = ArtifactResolver(
            slug="fp8", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        (tmp_settings.reviews_dir / "fp8_phase_0_task_1_code_review_round1.md").write_text("")
        assert r.scan_existing_rounds() == (1, 0)

    def test_scan_review_and_response(self, tmp_settings):
        r = ArtifactResolver(
            slug="fp8", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        (tmp_settings.reviews_dir / "fp8_phase_0_task_1_code_review_round1.md").write_text("")
        (tmp_settings.reviews_dir / "fp8_phase_0_task_1_coder_response_round1.md").write_text("")
        assert r.scan_existing_rounds() == (1, 1)

    def test_scan_multiple_rounds(self, tmp_settings):
        r = ArtifactResolver(
            slug="fp8", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        for name in [
            "fp8_phase_0_task_1_code_review_round1.md",
            "fp8_phase_0_task_1_coder_response_round1.md",
            "fp8_phase_0_task_1_code_review_round2.md",
        ]:
            (tmp_settings.reviews_dir / name).write_text("")
        assert r.scan_existing_rounds() == (2, 1)

    def test_scan_ignores_other_slugs(self, tmp_settings):
        r = ArtifactResolver(
            slug="my_slug", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        # Create artifacts for a different slug
        (tmp_settings.reviews_dir / "other_phase_0_task_1_code_review_round1.md").write_text("")
        assert r.scan_existing_rounds() == (0, 0)

    def test_scan_plan_mode_simple(self, tmp_settings):
        r = ArtifactResolver(
            slug="my_plan", mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings, stage_label=None,
        )
        (tmp_settings.reviews_dir / "my_plan_plan_review_round1.md").write_text("")
        (tmp_settings.reviews_dir / "my_plan_plan_update_round1.md").write_text("")
        assert r.scan_existing_rounds() == (1, 1)

    def test_scan_plan_mode_stage(self, tmp_settings):
        r = ArtifactResolver(
            slug="fp8", mode=Mode.PLAN, phase=0, task=0,
            settings=tmp_settings, stage_label="phase_0_foundation",
        )
        (tmp_settings.reviews_dir / "fp8_phase_0_foundation_review_round1.md").write_text("")
        assert r.scan_existing_rounds() == (1, 0)
