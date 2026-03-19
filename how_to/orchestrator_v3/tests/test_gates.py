"""Acceptance gate verification tests for orchestrator_v3 Phase 0.

Each test maps to a specific acceptance gate in
``active_plans/orchestrator_v3/phases/phase_0_core_fixes.md``.
"""

from __future__ import annotations

import pytest

from orchestrator_v3.artifacts import ArtifactResolver
from orchestrator_v3.config import Mode, PlanType, Status
from orchestrator_v3.loop import OrchestratorLoop
from orchestrator_v3.prompts import PromptBuilder
from orchestrator_v3.reviewer import MockReviewer
from orchestrator_v3.state import (
    CampaignManager,
    StateManager,
    TaskStateManager,
    campaign_index_path,
    task_state_path,
)


# ── Helpers ────────────────────────────────────────────────────────────


class StubDisplay:
    """Minimal display stub that records calls."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def stub(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return stub


# ── Gate 1: Prompt label uses resolver, not state ──────────────────────


class TestGate1PromptLabelUsesResolverNotState:
    """Gate 1: _build_prompt() uses resolver phase/task, never state."""

    def test_prompt_label_uses_resolver_not_state(self, tmp_settings):
        # Resolver says phase=2, task=5
        resolver = ArtifactResolver(
            slug="gate1", mode=Mode.CODE, phase=2, task=5,
            settings=tmp_settings,
        )
        # State says phase=0, task=1 (drift scenario)
        sm = StateManager(
            state_path=tmp_settings.reviews_dir / "gate1_orchestrator_state.json",
            settings=tmp_settings,
        )
        sm.init(
            plan_slug="gate1", mode=Mode.CODE, plan_file="p.md",
            plan_type=PlanType.SIMPLE,
        )
        pb = PromptBuilder(artifact_resolver=resolver, mode=Mode.CODE, slug="gate1")
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir()
        reviewer = MockReviewer(mock_dir=mock_dir)
        loop = OrchestratorLoop(
            state_manager=sm, artifact_resolver=resolver,
            prompt_builder=pb, reviewer=reviewer,
            display=StubDisplay(), settings=tmp_settings,
            skip_preflight=True,
        )
        prompt = loop._build_prompt(1)
        assert "Phase 2, Task 5" in prompt
        assert "Phase 0, Task 1" not in prompt


# ── Gate 2: Per-task state file creation ──────────────────────────────


class TestGate2PerTaskStateFileCreation:
    """Gate 2: Code mode creates per-task state files at the correct path."""

    def test_per_task_state_file_creation(self, tmp_settings):
        path = task_state_path("gate2", 1, 3, tmp_settings)
        tsm = TaskStateManager(state_path=path)
        tsm.init(slug="gate2", phase=1, task=3, plan_file="p.md")

        assert path.exists()
        assert path.name == "gate2_p1_t3_state.json"
        state = tsm.load()
        assert state.slug == "gate2"
        assert state.phase == 1
        assert state.task == 3


# ── Gate 3: Campaign index advance_task ──────────────────────────────


class TestGate3CampaignIndexAdvanceTask:
    """Gate 3: Campaign index tracks progress and advance_task updates it."""

    def test_campaign_index_advance_task(self, tmp_settings):
        ci_path = campaign_index_path("gate3", tmp_settings)
        cm = CampaignManager(state_path=ci_path, settings=tmp_settings)
        cm.init(
            slug="gate3", mode=Mode.CODE, plan_file="p.md",
            total_phases=1, tasks_per_phase={"0": 3},
        )

        # Create per-task state for task 1
        ts_path = task_state_path("gate3", 0, 1, tmp_settings)
        tsm = TaskStateManager(state_path=ts_path)
        tsm.init(slug="gate3", phase=0, task=1, plan_file="p.md")

        # Advance: task 1 → task 2
        new_state = cm.advance_task()
        assert new_state.current_task == 2
        assert new_state.current_phase == 0

        # Per-task state for task 1 is now APPROVED
        ts1 = TaskStateManager(state_path=ts_path).load()
        assert ts1.status == Status.APPROVED.value


# ── Gate 4: Code prompt targets code_complete for all rounds ─────────


class TestGate4CodePromptTargetsCodeCompleteAllRounds:
    """Gate 4: build_code_prompt() targets code_complete_round{R} for all rounds."""

    def test_code_prompt_targets_code_complete_all_rounds(self, tmp_settings):
        resolver = ArtifactResolver(
            slug="gate4", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        pb = PromptBuilder(artifact_resolver=resolver, mode=Mode.CODE, slug="gate4")

        for round_num in (1, 2, 3):
            prompt = pb.build_code_prompt(
                round_num=round_num, phase=0, task=1,
                plan_file="p.md", phase_file=None,
            )
            expected = str(resolver.complete_path(round_num))
            assert f"CODE ARTIFACT TO REVIEW: {expected}" in prompt


# ── Gate 6: Per-task state isolation ─────────────────────────────────


class TestGate6PerTaskStateIsolation:
    """Gate 6 (supplementary): Two tasks have independent state."""

    def test_per_task_state_isolation(self, tmp_settings):
        tsm1 = TaskStateManager(
            state_path=task_state_path("gate6", 0, 1, tmp_settings)
        )
        tsm2 = TaskStateManager(
            state_path=task_state_path("gate6", 0, 2, tmp_settings)
        )
        tsm1.init(slug="gate6", phase=0, task=1, plan_file="p.md")
        tsm2.init(slug="gate6", phase=0, task=2, plan_file="p.md")

        # Modify task 1
        tsm1.update(status=Status.APPROVED.value, current_round=5)

        # Task 2 unaffected
        s2 = tsm2.load()
        assert s2.status == Status.NEEDS_REVIEW.value
        assert s2.current_round == 1

        # Task 1 has changes
        s1 = tsm1.load()
        assert s1.status == Status.APPROVED.value
        assert s1.current_round == 5


# ── Gate 7: Pydantic extra="forbid" ─────────────────────────────────


class TestGate7PydanticExtraForbid:
    """Gate 7: All Pydantic state models reject unknown fields."""

    @pytest.mark.parametrize("model_cls", [
        pytest.param("OrchestratorState", id="OrchestratorState"),
        pytest.param("TaskState", id="TaskState"),
        pytest.param("CampaignIndex", id="CampaignIndex"),
    ])
    def test_extra_forbid_rejects_unknown_fields(self, model_cls):
        from pydantic import ValidationError
        from orchestrator_v3 import state as state_mod

        cls = getattr(state_mod, model_cls)
        # OrchestratorState needs extra required fields
        if model_cls == "OrchestratorState":
            with pytest.raises(ValidationError):
                cls(
                    plan_slug="x", mode="code", plan_file="p.md",
                    plan_type="simple", phantom_field="bad",
                )
        elif model_cls == "TaskState":
            with pytest.raises(ValidationError):
                cls(slug="x", phase=0, task=1, phantom_field="bad")
        else:  # CampaignIndex
            with pytest.raises(ValidationError):
                cls(slug="x", phantom_field="bad")


# ── Gates 5-6: Complex plan stage handling ───────────────────────────


class TestGate5And6ComplexPlanStageResolver:
    """Gates 5-6 + Task 7.2/D7: Complex plan ArtifactResolver uses stage_label,
    stage advance is idempotent, and resume is stage-scoped.

    These tests verify behavior after Task 7 fixes are applied.
    """

    def test_complex_plan_stage_resolver_omits_phase_task(self, tmp_settings):
        """D7: Stage-specific ArtifactResolver must NOT copy phase/task from state.

        To detect the bug: set state.current_phase to a sentinel value (99),
        then verify the stage resolver did NOT inherit it. With the bug,
        the resolver gets phase=99 from state; after Task 7.2 fix, it won't.
        """
        slug = "gate56"
        plan_dir = tmp_settings.active_plans_dir / slug
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)
        (plan_dir / f"{slug}_master_plan.md").write_text("# Master Plan\n")
        (phases_dir / "phase_0_test.md").write_text(
            "# Phase 0\n\n### [ ] 1 Task\n"
        )

        sm = StateManager(
            state_path=tmp_settings.reviews_dir / f"{slug}_orchestrator_state.json",
            settings=tmp_settings,
        )
        sm.init(
            plan_slug=slug, mode=Mode.PLAN, plan_file="p.md",
            plan_type=PlanType.COMPLEX, total_stages=2,
            stage_files=[
                str(phases_dir / "phase_0_test.md"),
                str(plan_dir / f"{slug}_master_plan.md"),
            ],
        )
        # Set state phase AND task to sentinels to detect if resolver copies them
        sm.update(current_phase=99, current_task=99)

        resolver = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=1,
            settings=tmp_settings,
        )
        pb = PromptBuilder(artifact_resolver=resolver, mode=Mode.PLAN, slug=slug)
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir()
        reviewer = MockReviewer(mock_dir=mock_dir)
        loop = OrchestratorLoop(
            state_manager=sm, artifact_resolver=resolver,
            prompt_builder=pb, reviewer=reviewer,
            display=StubDisplay(), settings=tmp_settings,
            skip_preflight=True,
        )

        state = sm.load()
        loop._run_complex_plan(1, 5, state)

        # Stage resolver must have stage_label set
        assert loop.artifact_resolver.stage_label is not None
        # Stage resolver must NOT have inherited phase=99 or task=99 from state
        assert loop.artifact_resolver.phase != 99, (
            "Stage-specific resolver copied vestigial phase from state"
        )
        assert loop.artifact_resolver.task != 99, (
            "Stage-specific resolver copied vestigial task from state"
        )

    def test_complex_plan_stage_scoped_resume(self, tmp_settings):
        """Gate 6: Resume scans only current-stage artifacts, not all slugs.

        Creates artifacts for stage 0 (approved) and stage 1 (round 1 review
        exists). Verifies determine_resume_point with stage 1's resolver
        returns round 1 status, not stage 0's artifacts.
        """
        from orchestrator_v3.loop import determine_resume_point

        slug = "gate6r"
        plan_dir = tmp_settings.active_plans_dir / slug
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)
        (plan_dir / f"{slug}_master_plan.md").write_text("# Master\n")
        (phases_dir / "phase_0_test.md").write_text("# Phase 0\n")
        (phases_dir / "phase_1_test.md").write_text("# Phase 1\n")

        reviews = tmp_settings.reviews_dir

        # Stage 0 artifacts: round 1 review (approved) + round 1 update
        stage0_label = "phase_0_test"
        (reviews / f"{slug}_{stage0_label}_review_round1.md").write_text(
            "<!-- ORCH_META\nVERDICT: APPROVED\nBLOCKER: 0\n"
            "MAJOR: 0\nMINOR: 0\nDECISIONS: 0\nVERIFIED: 1\n-->\n# Approved\n"
        )

        # Stage 1 artifacts: round 1 review (fixes_required)
        stage1_label = "phase_1_test"
        (reviews / f"{slug}_{stage1_label}_review_round1.md").write_text(
            "<!-- ORCH_META\nVERDICT: FIXES_REQUIRED\nBLOCKER: 1\n"
            "MAJOR: 0\nMINOR: 0\nDECISIONS: 0\nVERIFIED: 0\n-->\n# Fixes\n"
        )

        # Create stage 1 resolver (with stage_label for scoping)
        stage1_resolver = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=1,
            settings=tmp_settings, stage_label=stage1_label,
        )

        # Resume for stage 1 should find round 1 review (needs_response)
        round_num, action = determine_resume_point(stage1_resolver)
        assert round_num == 1
        assert action == "needs_response"

    def test_complex_plan_idempotent_advance(self, tmp_settings):
        """Gate 5: Calling handle_approval twice at the same stage should
        not double-advance (uses 3 stages to avoid boundary masking)."""
        slug = "gate5"
        plan_dir = tmp_settings.active_plans_dir / slug
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)
        (plan_dir / f"{slug}_master_plan.md").write_text("# Master\n")
        (phases_dir / "phase_0_test.md").write_text("# Phase 0\n")
        (phases_dir / "phase_1_test.md").write_text("# Phase 1\n")

        sm = StateManager(
            state_path=tmp_settings.reviews_dir / f"{slug}_orchestrator_state.json",
            settings=tmp_settings,
        )
        sm.init(
            plan_slug=slug, mode=Mode.PLAN, plan_file="p.md",
            plan_type=PlanType.COMPLEX, total_stages=3,
            stage_files=[
                str(phases_dir / "phase_0_test.md"),
                str(phases_dir / "phase_1_test.md"),
                str(plan_dir / f"{slug}_master_plan.md"),
            ],
        )

        resolver = ArtifactResolver(
            slug=slug, mode=Mode.PLAN, phase=0, task=1,
            settings=tmp_settings,
        )
        pb = PromptBuilder(artifact_resolver=resolver, mode=Mode.PLAN, slug=slug)
        mock_dir = tmp_settings.reviews_dir / "mock"
        mock_dir.mkdir()
        reviewer = MockReviewer(mock_dir=mock_dir)
        loop = OrchestratorLoop(
            state_manager=sm, artifact_resolver=resolver,
            prompt_builder=pb, reviewer=reviewer,
            display=StubDisplay(), settings=tmp_settings,
            skip_preflight=True,
        )

        # Call handle_approval twice at stage 0
        loop.handle_approval(1)
        state_after_first = sm.load()
        loop.handle_approval(1)
        state_after_second = sm.load()

        # Stage should advance only once (0 → 1), not twice (0 → 2)
        assert state_after_first.current_stage == 1
        assert state_after_second.current_stage == 1
