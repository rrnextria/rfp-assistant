"""Unit tests for orchestrator_v3 reviewer and loop modules."""

import pytest

from orchestrator_v3.artifacts import ArtifactResolver
from orchestrator_v3.config import Mode, PlanType, Status
from orchestrator_v3.loop import (
    OrchestratorLoop,
    ReviewOutcome,
    determine_resume_point,
)
from orchestrator_v3.prompts import PromptBuilder
from orchestrator_v3.reviewer import MockReviewer, ReviewerBase


# ── Helpers ──────────────────────────────────────────────────────────

APPROVED_ORCH_META = """\
<!-- ORCH_META
VERDICT: APPROVED
BLOCKER: 0
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 5
-->

# Review
All good.
"""

FIXES_REQUIRED_ORCH_META = """\
<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 1
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 3
-->

# Review
B1: Something is wrong.
"""


class StubDisplay:
    """Minimal display stub that records calls."""

    def __init__(self):
        self.calls = []

    def print_round_header(self, round_num, max_rounds=0, stage_label=None):
        self.calls.append(("round_header", round_num))

    def print_approved_banner(self, **kwargs):
        self.calls.append(("approved_banner", kwargs))

    def print_waiting_banner(self, mode, round, review_file, response_file, plan_type=None, stage_label=None):
        self.calls.append(("waiting_banner", round, mode, review_file, response_file))

    def print_max_rounds_banner(self, max_rounds, mode="", stage_label=None):
        self.calls.append(("max_rounds_banner", max_rounds))

    def print_retry_banner(self):
        self.calls.append(("retry_banner",))

    def print_dry_run(self, prompt):
        self.calls.append(("dry_run", prompt))

    def print_stage_header(self, stage_idx, total_stages, stage_label, stage_file):
        self.calls.append(("stage_header", stage_idx, total_stages, stage_label))


class FailReviewer:
    """A reviewer that always returns False (simulates failure)."""

    def run_review(self, prompt, review_file, log_file):
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("[FailReviewer] Simulated failure\n")
        return False


@pytest.fixture
def code_resolver(tmp_settings):
    return ArtifactResolver(
        slug="test_slug",
        mode=Mode.CODE,
        phase=0,
        task=1,
        settings=tmp_settings,
    )


@pytest.fixture
def mock_dir(tmp_path):
    d = tmp_path / "mocks"
    d.mkdir()
    return d


def _make_loop(tmp_settings, code_resolver, reviewer, display=None):
    """Helper to create an OrchestratorLoop with standard dependencies."""
    from orchestrator_v3.state import StateManager

    state_path = tmp_settings.reviews_dir / "test_orchestrator_state.json"
    sm = StateManager(state_path=state_path, settings=tmp_settings)
    sm.init(
        plan_slug="test_slug",
        mode=Mode.CODE,
        plan_file="test_plan.md",
        plan_type=PlanType.SIMPLE,
        total_phases=1,
        tasks_per_phase={"0": 1},
    )
    pb = PromptBuilder(
        artifact_resolver=code_resolver,
        mode=Mode.CODE,
        slug="test_slug",
    )
    if display is None:
        display = StubDisplay()
    loop = OrchestratorLoop(
        state_manager=sm,
        artifact_resolver=code_resolver,
        prompt_builder=pb,
        reviewer=reviewer,
        display=display,
        settings=tmp_settings,
        skip_preflight=True,
    )
    return loop, sm, display


# ── Task 1: Reviewer tests ──────────────────────────────────────────

class TestMockReviewer:
    """4.1/4.2: MockReviewer copies correct files and handles missing files."""

    def test_copies_round1(self, mock_dir, tmp_path):
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)
        reviewer = MockReviewer(mock_dir=mock_dir)
        review_file = tmp_path / "reviews" / "test_slug_phase_0_task_1_code_review_round1.md"
        log_file = tmp_path / "logs" / "round1.log"

        result = reviewer.run_review("prompt", review_file, log_file)

        assert result is True
        assert review_file.exists()
        assert review_file.read_text() == APPROVED_ORCH_META
        assert "Copied" in log_file.read_text()

    def test_copies_round2(self, mock_dir, tmp_path):
        content2 = FIXES_REQUIRED_ORCH_META
        (mock_dir / "round2_review.md").write_text(content2)
        reviewer = MockReviewer(mock_dir=mock_dir)
        review_file = tmp_path / "reviews" / "test_slug_phase_0_task_1_code_review_round2.md"
        log_file = tmp_path / "logs" / "round2.log"

        result = reviewer.run_review("prompt", review_file, log_file)

        assert result is True
        assert review_file.read_text() == content2
        assert "Copied" in log_file.read_text()

    def test_copies_round3(self, mock_dir, tmp_path):
        content3 = APPROVED_ORCH_META
        (mock_dir / "round3_review.md").write_text(content3)
        reviewer = MockReviewer(mock_dir=mock_dir)
        review_file = tmp_path / "reviews" / "test_slug_phase_0_task_1_code_review_round3.md"
        log_file = tmp_path / "logs" / "round3.log"

        result = reviewer.run_review("prompt", review_file, log_file)

        assert result is True
        assert review_file.read_text() == content3
        assert "Copied" in log_file.read_text()

    def test_missing_mock_file(self, mock_dir, tmp_path):
        reviewer = MockReviewer(mock_dir=mock_dir)
        review_file = tmp_path / "reviews" / "test_slug_phase_0_task_1_code_review_round1.md"
        log_file = tmp_path / "logs" / "round1.log"

        result = reviewer.run_review("prompt", review_file, log_file)

        assert result is False
        assert not review_file.exists()
        assert "not found" in log_file.read_text()


class TestReviewerProtocol:
    """Verify MockReviewer satisfies ReviewerBase protocol."""

    def test_isinstance_check(self, mock_dir):
        reviewer = MockReviewer(mock_dir=mock_dir)
        assert isinstance(reviewer, ReviewerBase)


# ── Task 2: Resume detection tests ──────────────────────────────────

class TestResumeDetection:
    """4.3/4.4/4.5: Resume detection scans filesystem correctly."""

    def test_no_artifacts_yields_round1(self, code_resolver):
        round_num, action = determine_resume_point(code_resolver)
        assert round_num == 1
        assert action == "run_reviewer"

    def test_review_without_response_needs_response(self, code_resolver):
        review_file = code_resolver.review_path(1)
        review_file.write_text(FIXES_REQUIRED_ORCH_META)

        round_num, action = determine_resume_point(code_resolver)
        assert round_num == 1
        assert action == "needs_response"

    def test_review_approved_without_response(self, code_resolver):
        review_file = code_resolver.review_path(1)
        review_file.write_text(APPROVED_ORCH_META)

        round_num, action = determine_resume_point(code_resolver)
        assert round_num == 1
        assert action == "already_approved"

    def test_review_and_response_yields_next_round(self, code_resolver):
        code_resolver.review_path(1).write_text(FIXES_REQUIRED_ORCH_META)
        code_resolver.response_path(1).write_text("# Response\n")

        round_num, action = determine_resume_point(code_resolver)
        assert round_num == 2
        assert action == "run_reviewer"


class TestResumeLoop:
    """Verify loop.run(resume=True) for the needs_response path."""

    def test_resume_needs_response_prints_waiting(self, tmp_settings, code_resolver, mock_dir):
        """Resume with existing FIXES_REQUIRED review prints waiting banner."""
        (mock_dir / "round1_review.md").write_text(FIXES_REQUIRED_ORCH_META)
        code_resolver.complete_path(1).write_text("# Code Complete\n")

        reviewer = MockReviewer(mock_dir=mock_dir)
        loop, sm, display = _make_loop(tmp_settings, code_resolver, reviewer)

        # First run: creates review round 1
        loop.run(start_round=1, max_rounds=5)

        # Now resume — review exists but no response → needs_response
        loop2, sm2, display2 = _make_loop(tmp_settings, code_resolver, reviewer, display=StubDisplay())
        result = loop2.run(start_round=1, max_rounds=5, resume=True)

        assert result == 0
        waiting_calls = [c for c in display2.calls if c[0] == "waiting_banner"]
        assert len(waiting_calls) == 1
        # Assert correct round was passed (not 0 from a default)
        assert waiting_calls[0][1] == 1  # round == 1


# ── Task 3: Loop tests ──────────────────────────────────────────────

class TestLoopApproved:
    """4.6: Single round approved exits with success."""

    def test_single_round_approved(self, tmp_settings, code_resolver, mock_dir):
        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)
        code_resolver.complete_path(1).write_text("# Code Complete\n")

        reviewer = MockReviewer(mock_dir=mock_dir)
        loop, sm, display = _make_loop(tmp_settings, code_resolver, reviewer)

        result = loop.run(start_round=1, max_rounds=5)

        assert result == 0
        state = sm.load()
        assert state.status in (Status.APPROVED.value, Status.COMPLETE.value)
        approved_calls = [c for c in display.calls if c[0] == "approved_banner"]
        assert len(approved_calls) == 1


class TestLoopNotApproved:
    """4.7: Round 1 not approved triggers pause and exits 0."""

    def test_not_approved_pauses(self, tmp_settings, code_resolver, mock_dir):
        (mock_dir / "round1_review.md").write_text(FIXES_REQUIRED_ORCH_META)
        code_resolver.complete_path(1).write_text("# Code Complete\n")

        reviewer = MockReviewer(mock_dir=mock_dir)
        loop, sm, display = _make_loop(tmp_settings, code_resolver, reviewer)

        result = loop.run(start_round=1, max_rounds=5)

        assert result == 0
        state = sm.load()
        assert state.status == Status.NEEDS_RESPONSE.value
        waiting_calls = [c for c in display.calls if c[0] == "waiting_banner"]
        assert len(waiting_calls) == 1


class TestLoopMaxRounds:
    """4.8: Max rounds reached exits with error code 1."""

    def test_max_rounds_exit_1(self, tmp_settings, code_resolver, mock_dir):
        (mock_dir / "round1_review.md").write_text(FIXES_REQUIRED_ORCH_META)
        code_resolver.complete_path(1).write_text("# Code Complete\n")

        reviewer = MockReviewer(mock_dir=mock_dir)
        loop, sm, display = _make_loop(tmp_settings, code_resolver, reviewer)

        result = loop.run(start_round=1, max_rounds=1)

        # max_rounds=1 + FIXES_REQUIRED on last round → exit 1 with max-rounds banner
        assert result == 1
        max_calls = [c for c in display.calls if c[0] == "max_rounds_banner"]
        assert len(max_calls) == 1
        # handle_pause should NOT have been called
        waiting_calls = [c for c in display.calls if c[0] == "waiting_banner"]
        assert len(waiting_calls) == 0


class TestLoopReviewerError:
    """4.9: Reviewer error returns exit code 1."""

    def test_reviewer_error_exits_1(self, tmp_settings, code_resolver):
        code_resolver.complete_path(1).write_text("# Code Complete\n")
        reviewer = FailReviewer()
        loop, sm, display = _make_loop(tmp_settings, code_resolver, reviewer)

        result = loop.run(start_round=1, max_rounds=5)

        assert result == 1
        state = sm.load()
        assert state.status == Status.NEEDS_REVIEW.value
        retry_calls = [c for c in display.calls if c[0] == "retry_banner"]
        assert len(retry_calls) == 1
        waiting_calls = [c for c in display.calls if c[0] == "waiting_banner"]
        assert len(waiting_calls) == 0


class TestLoopDryRun:
    """Dry run prints prompt and exits 0."""

    def test_dry_run(self, tmp_settings, code_resolver, mock_dir):
        reviewer = MockReviewer(mock_dir=mock_dir)
        loop, sm, display = _make_loop(tmp_settings, code_resolver, reviewer)

        result = loop.run(start_round=1, dry_run=True)

        assert result == 0
        dry_calls = [c for c in display.calls if c[0] == "dry_run"]
        assert len(dry_calls) == 1


class TestCodeArtifactHash:
    """3.7: verify_code_artifact checks per-round code_complete existence and stores hash."""

    def test_round1_stores_hash(self, tmp_settings, code_resolver):
        code_resolver.complete_path(1).write_text("content A")
        reviewer = FailReviewer()
        loop, sm, _ = _make_loop(tmp_settings, code_resolver, reviewer)

        assert loop.verify_code_artifact(1) is True
        state = sm.load()
        assert state.code_artifact_hash is not None
        assert len(state.code_artifact_hash) == 64

    def test_round2_with_own_artifact_passes(self, tmp_settings, code_resolver):
        """Each round checks its own code_complete_round{R} file."""
        code_resolver.complete_path(1).write_text("content A")
        code_resolver.complete_path(2).write_text("content B")
        reviewer = FailReviewer()
        loop, sm, _ = _make_loop(tmp_settings, code_resolver, reviewer)

        loop.verify_code_artifact(1)
        assert loop.verify_code_artifact(2) is True

    def test_round2_missing_artifact_fails(self, tmp_settings, code_resolver):
        """Round 2 fails if code_complete_round2 is missing (even if round1 exists)."""
        code_resolver.complete_path(1).write_text("content A")
        reviewer = FailReviewer()
        loop, sm, _ = _make_loop(tmp_settings, code_resolver, reviewer)

        loop.verify_code_artifact(1)
        assert loop.verify_code_artifact(2) is False

    def test_missing_artifact_fails(self, tmp_settings, code_resolver):
        reviewer = FailReviewer()
        loop, sm, _ = _make_loop(tmp_settings, code_resolver, reviewer)
        assert loop.verify_code_artifact(1) is False


class TestPromptLabelSourceOfTruth:
    """v3 fix: _build_prompt uses resolver phase/task, not state."""

    def test_prompt_uses_resolver_not_state(self, tmp_settings, mock_dir):
        """State has phase=0/task=1 but resolver has phase=2/task=5.
        Prompt must contain 'Phase 2, Task 5', not 'Phase 0, Task 1'."""
        from orchestrator_v3.state import StateManager

        # Create resolver for phase=2, task=5
        resolver = ArtifactResolver(
            slug="test_slug", mode=Mode.CODE, phase=2, task=5,
            settings=tmp_settings,
        )

        # State stays at phase=0, task=1 (simulating state drift)
        state_path = tmp_settings.reviews_dir / "test_orchestrator_state.json"
        sm = StateManager(state_path=state_path, settings=tmp_settings)
        sm.init(
            plan_slug="test_slug",
            mode=Mode.CODE,
            plan_file="test_plan.md",
            plan_type=PlanType.SIMPLE,
            total_phases=3,
            tasks_per_phase={"0": 5, "1": 5, "2": 5},
        )

        pb = PromptBuilder(
            artifact_resolver=resolver,
            mode=Mode.CODE,
            slug="test_slug",
        )

        reviewer = MockReviewer(mock_dir=mock_dir)
        loop = OrchestratorLoop(
            state_manager=sm,
            artifact_resolver=resolver,
            prompt_builder=pb,
            reviewer=reviewer,
            display=StubDisplay(),
            settings=tmp_settings,
            skip_preflight=True,
        )

        prompt = loop._build_prompt(1)
        assert "Phase 2, Task 5" in prompt
        assert "Phase 0, Task 1" not in prompt


class TestPerTaskStateIntegration:
    """3.7: Mock code review for 2 tasks creates separate state files."""

    def test_two_task_mock_review_separate_state(self, tmp_settings, mock_dir):
        """Run mock review for task 1 and task 2; verify independent state files."""
        from orchestrator_v3.state import TaskStateManager, task_state_path

        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        for task_num in (1, 2):
            # Per-task state
            ts_path = task_state_path("integ", 0, task_num, tmp_settings)
            tsm = TaskStateManager(state_path=ts_path)
            tsm.init(slug="integ", phase=0, task=task_num, plan_file="p.md")

            resolver = ArtifactResolver(
                slug="integ", mode=Mode.CODE, phase=0, task=task_num,
                settings=tmp_settings,
            )
            # Create code_complete artifact
            resolver.complete_path(1).write_text(f"# Code Complete Task {task_num}\n")

            pb = PromptBuilder(
                artifact_resolver=resolver, mode=Mode.CODE, slug="integ",
            )
            reviewer = MockReviewer(mock_dir=mock_dir)
            loop = OrchestratorLoop(
                state_manager=tsm,
                artifact_resolver=resolver,
                prompt_builder=pb,
                reviewer=reviewer,
                display=StubDisplay(),
                settings=tmp_settings,
                skip_preflight=True,
            )
            result = loop.run(start_round=1, max_rounds=5)
            assert result == 0

        # Verify separate state files exist
        path1 = task_state_path("integ", 0, 1, tmp_settings)
        path2 = task_state_path("integ", 0, 2, tmp_settings)
        assert path1.exists()
        assert path2.exists()
        assert path1 != path2

        # Both should be APPROVED
        tsm1 = TaskStateManager(state_path=path1)
        tsm2 = TaskStateManager(state_path=path2)
        state1 = tsm1.load()
        state2 = tsm2.load()
        assert state1.status == Status.APPROVED.value
        assert state2.status == Status.APPROVED.value
        assert state1.task == 1
        assert state2.task == 2

        # History should be independent
        assert len(state1.history) >= 1
        assert len(state2.history) >= 1


class TestCampaignAdvanceOnApproval:
    """4.7: Mock code review approves task 1, campaign advances to task 2."""

    def test_campaign_advances_on_approval(self, tmp_settings, mock_dir):
        from orchestrator_v3.state import (
            CampaignManager,
            TaskStateManager,
            campaign_index_path,
            task_state_path,
        )

        (mock_dir / "round1_review.md").write_text(APPROVED_ORCH_META)

        # Create campaign index with 2 tasks
        ci_path = campaign_index_path("camp", tmp_settings)
        cm = CampaignManager(state_path=ci_path, settings=tmp_settings)
        cm.init(
            slug="camp",
            mode=Mode.CODE,
            plan_file="p.md",
            total_phases=1,
            tasks_per_phase={"0": 2},
        )

        # Create per-task state for task 1
        ts_path = task_state_path("camp", 0, 1, tmp_settings)
        tsm = TaskStateManager(state_path=ts_path)
        tsm.init(slug="camp", phase=0, task=1, plan_file="p.md")

        resolver = ArtifactResolver(
            slug="camp", mode=Mode.CODE, phase=0, task=1,
            settings=tmp_settings,
        )
        resolver.complete_path(1).write_text("# Code Complete Task 1\n")

        pb = PromptBuilder(
            artifact_resolver=resolver, mode=Mode.CODE, slug="camp",
        )
        reviewer = MockReviewer(mock_dir=mock_dir)
        loop = OrchestratorLoop(
            state_manager=tsm,
            artifact_resolver=resolver,
            prompt_builder=pb,
            reviewer=reviewer,
            display=StubDisplay(),
            settings=tmp_settings,
            campaign_manager=cm,
            skip_preflight=True,
        )
        result = loop.run(start_round=1, max_rounds=5)
        assert result == 0

        # Campaign should advance to task 2
        campaign = cm.load()
        assert campaign.current_phase == 0
        assert campaign.current_task == 2
        assert campaign.status == Status.NEEDS_REVIEW.value

        # Per-task state for task 1 should be APPROVED
        ts = tsm.load()
        assert ts.status == Status.APPROVED.value
