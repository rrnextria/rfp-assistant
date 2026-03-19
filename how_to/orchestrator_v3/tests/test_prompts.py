"""Unit tests for orchestrator_v3.prompts module."""

import pytest

from orchestrator_v3.artifacts import ArtifactResolver
from orchestrator_v3.config import Mode
from orchestrator_v3.prompts import PromptBuilder


@pytest.fixture
def code_resolver(tmp_settings):
    """ArtifactResolver for code mode with known slug/phase/task."""
    return ArtifactResolver(
        slug="test_slug",
        mode=Mode.CODE,
        phase=0,
        task=1,
        settings=tmp_settings,
    )


@pytest.fixture
def plan_resolver(tmp_settings):
    """ArtifactResolver for plan mode."""
    return ArtifactResolver(
        slug="test_slug",
        mode=Mode.PLAN,
        phase=0,
        task=1,
        settings=tmp_settings,
    )


@pytest.fixture
def code_builder(code_resolver):
    return PromptBuilder(
        artifact_resolver=code_resolver,
        mode=Mode.CODE,
        slug="test_slug",
    )


@pytest.fixture
def plan_builder(plan_resolver):
    return PromptBuilder(
        artifact_resolver=plan_resolver,
        mode=Mode.PLAN,
        slug="test_slug",
    )


class TestPlanPromptRound1:
    """5.1: Plan prompt round 1 contains ORCH_META instructions, no prior context."""

    def test_simple_plan_round1_has_orch_meta(self, plan_builder):
        prompt = plan_builder.build_simple_plan_prompt(
            round_num=1, plan_file="test_plan.md", context=""
        )
        assert "ORCH_META" in prompt
        assert "<!-- ORCH_META" in prompt
        assert "VERDICT:" in prompt
        assert "-->" in prompt
        assert "round 0" not in prompt.lower()
        assert "Prior review" not in prompt

    def test_simple_plan_round1_has_review_output_path(self, plan_builder, plan_resolver):
        prompt = plan_builder.build_simple_plan_prompt(
            round_num=1, plan_file="test_plan.md", context=""
        )
        expected_path = str(plan_resolver.review_path(1))
        assert expected_path in prompt


class TestPlanPromptRound2:
    """5.2: Plan prompt round 2 contains prior review path and prior update path."""

    def test_plan_round2_has_prior_context(self, plan_builder, plan_resolver):
        context = plan_builder.build_plan_context(round_num=2)
        prompt = plan_builder.build_simple_plan_prompt(
            round_num=2, plan_file="test_plan.md", context=context
        )
        review_r1 = str(plan_resolver.review_path(1))
        response_r1 = str(plan_resolver.response_path(1))
        assert review_r1 in prompt
        assert response_r1 in prompt
        assert "RESOLVED" in prompt
        assert "STILL_OPEN" in prompt


class TestCodePromptRound1:
    """5.3: Code prompt round 1 contains ORCH_META instructions, no prior context."""

    def test_code_round1_has_orch_meta_and_checklist(self, code_builder, code_resolver):
        prompt = code_builder.build_code_prompt(
            round_num=1,
            phase=0,
            task=1,
            plan_file="master.md",
            phase_file="phase_0.md",
        )
        assert "ORCH_META" in prompt
        assert "<!-- ORCH_META" in prompt
        assert "finding" in prompt.lower() or "B1" in prompt
        complete_path = str(code_resolver.complete_path(1))
        assert complete_path in prompt
        review_out = str(code_resolver.review_path(1))
        assert review_out in prompt
        assert "Subtask Completeness" in prompt
        assert "SHA-256" in prompt
        assert "Prior review" not in prompt


class TestCodePromptRound3:
    """5.4: Code prompt round 3 contains round 2 review + response paths."""

    def test_code_round3_has_prior_context(self, code_builder, code_resolver):
        prompt = code_builder.build_code_prompt(
            round_num=3,
            phase=0,
            task=1,
            plan_file="master.md",
            phase_file="phase_0.md",
        )
        # Prior-round context paths must appear in the prompt itself
        review_r2 = str(code_resolver.review_path(2))
        response_r2 = str(code_resolver.response_path(2))
        assert review_r2 in prompt
        assert response_r2 in prompt
        # Artifact path must be complete_path(3), NOT response_path(2)
        expected_artifact = str(code_resolver.complete_path(3))
        assert expected_artifact in prompt


class TestCodePromptRound2ArtifactProtocol:
    """5.4b: Round 2 reviewer targets code_complete_round2, NOT coder_response_round1."""

    def test_round2_targets_code_complete(self, code_builder, code_resolver):
        prompt = code_builder.build_code_prompt(
            round_num=2,
            phase=0,
            task=1,
            plan_file="master.md",
            phase_file="phase_0.md",
        )
        expected = str(code_resolver.complete_path(2))
        assert expected in prompt
        wrong = str(code_resolver.response_path(1))
        # coder_response should appear only in prior-round context, not as review target
        assert f"CODE ARTIFACT TO REVIEW: {wrong}" not in prompt
        assert f"CODE ARTIFACT TO REVIEW: {expected}" in prompt


class TestSingleFilePlan:
    """5.5: Code prompt for single-file plan resolves correct plan path."""

    def test_single_file_plan_no_phase_file(self, code_builder):
        prompt = code_builder.build_code_prompt(
            round_num=1,
            phase=0,
            task=1,
            plan_file="active_plans/simple_slug.md",
            phase_file=None,
        )
        assert "active_plans/simple_slug.md" in prompt
        assert "Phase Plan:" not in prompt


class TestComplexPlan:
    """5.6: Code prompt for complex plan resolves master + phase file paths."""

    def test_complex_plan_has_both_paths(self, code_builder):
        prompt = code_builder.build_code_prompt(
            round_num=1,
            phase=2,
            task=1,
            plan_file="active_plans/complex_slug/complex_slug_master_plan.md",
            phase_file="active_plans/complex_slug/phases/phase_2_foo.md",
        )
        assert "active_plans/complex_slug/complex_slug_master_plan.md" in prompt
        assert "active_plans/complex_slug/phases/phase_2_foo.md" in prompt
        assert "Master Plan:" in prompt
        assert "Phase Plan:" in prompt


class TestOrchMetaExampleBlock:
    """5.7: Prompt text DOES contain a complete ORCH_META example block."""

    def test_all_prompt_types_contain_orch_meta_example(
        self, plan_builder, code_builder
    ):
        prompts = [
            plan_builder.build_simple_plan_prompt(1, "plan.md", ""),
            plan_builder.build_phase_review_prompt(
                1, "phase_0.md", "master.md", ""
            ),
            plan_builder.build_master_review_prompt(
                1, "master.md", ["phase_0.md"], ""
            ),
            code_builder.build_code_prompt(
                1, 0, 1, "master.md", "phase_0.md"
            ),
            code_builder.build_code_prompt(
                1, 0, 1, "plan.md", None
            ),
        ]
        for i, prompt in enumerate(prompts):
            assert "<!-- ORCH_META" in prompt, f"Prompt {i} missing ORCH_META opening"
            assert "VERDICT:" in prompt, f"Prompt {i} missing VERDICT"
            assert "-->" in prompt, f"Prompt {i} missing closing tag"


class TestFindingIdInstructions:
    """5.8: Finding ID instructions present in all prompt types."""

    def test_all_prompt_types_have_finding_ids(
        self, plan_builder, code_builder
    ):
        prompts = [
            plan_builder.build_simple_plan_prompt(1, "plan.md", ""),
            plan_builder.build_phase_review_prompt(
                1, "phase_0.md", "master.md", ""
            ),
            plan_builder.build_master_review_prompt(
                1, "master.md", ["phase_0.md"], ""
            ),
            code_builder.build_code_prompt(
                1, 0, 1, "master.md", "phase_0.md"
            ),
            code_builder.build_code_prompt(
                1, 0, 1, "plan.md", None
            ),
        ]
        for i, prompt in enumerate(prompts):
            assert "B1" in prompt, f"Prompt {i} missing B1 finding ID convention"
            assert "M1" in prompt, f"Prompt {i} missing M1 finding ID convention"


class TestPriorRoundContext:
    """Additional tests for prior-round context builders."""

    def test_plan_context_round1_empty(self, plan_builder):
        """4.3: Round 1 returns empty context."""
        assert plan_builder.build_plan_context(1) == ""

    def test_code_context_round1_empty(self, code_builder):
        """4.3: Round 1 returns empty context."""
        assert code_builder.build_code_context(1) == ""

    def test_plan_context_round3_has_round2_paths(self, plan_builder, plan_resolver):
        """4.4: Round 3 context contains round 2 review + response paths."""
        ctx = plan_builder.build_plan_context(3)
        assert str(plan_resolver.review_path(2)) in ctx
        assert str(plan_resolver.response_path(2)) in ctx
        assert "Planner update" in ctx

    def test_code_context_round3_has_round2_paths(self, code_builder, code_resolver):
        """4.4: Round 3 context contains round 2 review + response paths."""
        ctx = code_builder.build_code_context(3)
        assert str(code_resolver.review_path(2)) in ctx
        assert str(code_resolver.response_path(2)) in ctx
        assert "Coder response" in ctx
