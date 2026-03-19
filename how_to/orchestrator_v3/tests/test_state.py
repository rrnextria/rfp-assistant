"""Unit tests for orchestrator_v3.state module."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from orchestrator_v3.config import Mode, PlanType, Status
from orchestrator_v3.state import (
    CampaignIndex,
    CampaignManager,
    OrchestratorState,
    StateManager,
    TaskState,
    TaskStateManager,
    campaign_index_path,
    task_state_path,
)


class TestStateInit:
    def test_init_creates_state_file(self, tmp_state_manager):
        state = tmp_state_manager.init(
            plan_slug="test",
            mode=Mode.CODE,
            plan_file="active_plans/test/test_master_plan.md",
            plan_type=PlanType.COMPLEX,
        )
        assert tmp_state_manager.state_path.exists()
        assert state.current_phase == 0
        assert state.current_task == 1
        assert state.current_round == 1
        assert state.status == Status.NEEDS_REVIEW.value

    def test_init_sets_stage_fields(self, tmp_state_manager):
        state = tmp_state_manager.init(
            plan_slug="test",
            mode=Mode.PLAN,
            plan_file="test.md",
            plan_type=PlanType.COMPLEX,
            total_stages=3,
            stage_files=["a.md", "b.md", "c.md"],
            current_stage=0,
        )
        assert state.total_stages == 3
        assert state.stage_files == ["a.md", "b.md", "c.md"]
        assert state.current_stage == 0


class TestStateLoadSave:
    def test_load_roundtrip(self, tmp_state_manager):
        original = tmp_state_manager.init(
            plan_slug="roundtrip",
            mode=Mode.CODE,
            plan_file="test.md",
            plan_type=PlanType.SIMPLE,
            total_phases=2,
            tasks_per_phase={"0": 3, "1": 2},
            total_stages=4,
            stage_files=["a.md", "b.md"],
            current_stage=1,
        )
        loaded = tmp_state_manager.load()
        # Verify ALL fields match after JSON round-trip
        assert loaded.plan_slug == original.plan_slug
        assert loaded.mode == original.mode
        assert loaded.plan_file == original.plan_file
        assert loaded.plan_type == original.plan_type
        assert loaded.current_phase == original.current_phase
        assert loaded.current_task == original.current_task
        assert loaded.current_round == original.current_round
        assert loaded.status == original.status
        assert loaded.started_at == original.started_at
        assert loaded.last_updated == original.last_updated
        assert loaded.total_phases == original.total_phases
        assert loaded.tasks_per_phase == original.tasks_per_phase
        assert loaded.current_stage == original.current_stage
        assert loaded.total_stages == original.total_stages
        assert loaded.stage_files == original.stage_files
        assert loaded.code_artifact_hash == original.code_artifact_hash
        assert loaded.history == original.history

    def test_load_missing_file_raises(self, tmp_settings):
        sm = StateManager(
            state_path=tmp_settings.reviews_dir / "nonexistent.json",
            settings=tmp_settings,
        )
        with pytest.raises(FileNotFoundError):
            sm.load()

    def test_save_creates_backup(self, tmp_state_manager):
        tmp_state_manager.init(
            plan_slug="bak",
            mode=Mode.CODE,
            plan_file="t.md",
            plan_type=PlanType.SIMPLE,
        )
        # Read the initial content for comparison
        original_content = tmp_state_manager.state_path.read_text()
        # Update with a field change and save again to trigger backup
        tmp_state_manager.update(status=Status.NEEDS_RESPONSE.value)
        bak_path = str(tmp_state_manager.state_path) + ".bak"
        assert os.path.exists(bak_path)
        # Verify .bak contains the previous state content
        bak_content = open(bak_path).read()
        assert '"needs_review"' in bak_content
        assert '"needs_response"' not in bak_content

    def test_save_atomic_write(self, tmp_state_manager):
        tmp_state_manager.init(
            plan_slug="atomic",
            mode=Mode.CODE,
            plan_file="t.md",
            plan_type=PlanType.SIMPLE,
        )
        state = tmp_state_manager.load()

        calls = []
        original_replace = os.replace

        def mock_replace(src, dst):
            calls.append((src, dst))
            return original_replace(src, dst)

        with patch("orchestrator_v3.state.os.replace", side_effect=mock_replace):
            tmp_state_manager.save(state)

        assert len(calls) == 1
        src, dst = calls[0]
        assert src.endswith(".tmp")
        assert str(dst) == str(tmp_state_manager.state_path)
        # Verify same directory
        assert os.path.dirname(src) == str(tmp_state_manager.state_path.parent)


class TestEnumValidation:
    def test_rejects_invalid_mode(self):
        with pytest.raises(ValidationError):
            OrchestratorState(
                plan_slug="t", mode="bogus", plan_file="t.md",
                plan_type=PlanType.SIMPLE,
            )

    def test_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            OrchestratorState(
                plan_slug="t", mode=Mode.CODE, plan_file="t.md",
                plan_type=PlanType.SIMPLE, status="bogus",
            )

    def test_accepts_valid_enum_string(self):
        state = OrchestratorState(
            plan_slug="t", mode="code", plan_file="t.md",
            plan_type="simple",
        )
        assert state.mode == Mode.CODE.value
        assert state.plan_type == PlanType.SIMPLE.value


class TestStateUpdate:
    def test_update_changes_field(self, tmp_state_manager):
        tmp_state_manager.init(
            plan_slug="upd",
            mode=Mode.CODE,
            plan_file="t.md",
            plan_type=PlanType.SIMPLE,
        )
        original = tmp_state_manager.load()
        updated = tmp_state_manager.update(
            status=Status.NEEDS_RESPONSE.value
        )
        assert updated.status == Status.NEEDS_RESPONSE.value
        assert updated.last_updated >= original.last_updated

    def test_update_rejects_invalid_field(self, tmp_state_manager):
        tmp_state_manager.init(
            plan_slug="inv",
            mode=Mode.CODE,
            plan_file="t.md",
            plan_type=PlanType.SIMPLE,
        )
        with pytest.raises(ValueError, match="Unknown state fields"):
            tmp_state_manager.update(nonexistent_field="x")


class TestAdvanceTask:
    def test_advance_task_within_phase(self, tmp_state_manager):
        tmp_state_manager.init(
            plan_slug="adv",
            mode=Mode.CODE,
            plan_file="t.md",
            plan_type=PlanType.SIMPLE,
            total_phases=1,
            tasks_per_phase={"0": 3},
        )
        state = tmp_state_manager.advance_task()
        assert state.current_task == 2
        assert state.current_phase == 0

    def test_advance_task_cross_phase(self, tmp_state_manager):
        tmp_state_manager.init(
            plan_slug="cross",
            mode=Mode.CODE,
            plan_file="t.md",
            plan_type=PlanType.SIMPLE,
            total_phases=2,
            tasks_per_phase={"0": 1, "1": 2},
        )
        state = tmp_state_manager.advance_task()
        assert state.current_phase == 1
        assert state.current_task == 1
        assert state.current_round == 1

    def test_advance_task_offbyone_regression(self, tmp_state_manager):
        """Critical regression: v1 used > instead of >=, allowing phase 5."""
        tmp_state_manager.init(
            plan_slug="obo",
            mode=Mode.CODE,
            plan_file="t.md",
            plan_type=PlanType.SIMPLE,
            total_phases=5,
            tasks_per_phase={
                "0": 1, "1": 1, "2": 1, "3": 1, "4": 1,
            },
        )
        # Advance to phase 4, task 1 (the last valid position)
        for _ in range(4):
            tmp_state_manager.advance_task()
        # Now at phase 4, task 1 — advancing should COMPLETE
        state = tmp_state_manager.advance_task()
        assert state.status == Status.COMPLETE.value


class TestRecordRound:
    def test_record_round_appends_history(self, tmp_state_manager):
        tmp_state_manager.init(
            plan_slug="hist",
            mode=Mode.CODE,
            plan_file="t.md",
            plan_type=PlanType.SIMPLE,
        )
        tmp_state_manager.record_round(
            round_num=1,
            action="review",
            outcome="fixes_required",
            artifact_path="reviews/test_review_round1.md",
            verdict="FIXES_REQUIRED",
            blocker=1,
            major=2,
            minor=0,
        )
        tmp_state_manager.record_round(
            round_num=2,
            action="review",
            outcome="approved",
            artifact_path="reviews/test_review_round2.md",
            verdict="APPROVED",
            blocker=0,
            major=0,
            minor=0,
        )
        state = tmp_state_manager.load()
        assert len(state.history) == 2
        assert state.history[0]["round"] == 1
        assert state.history[0]["verdict"] == "FIXES_REQUIRED"
        assert state.history[0]["blocker"] == 1
        assert state.history[1]["round"] == 2
        assert state.history[1]["verdict"] == "APPROVED"
        assert "timestamp" in state.history[0]


# ── Per-Task State (v3 additions) ──────────────────────────────────────


class TestTaskStatePath:
    """3.6: task_state_path computes correct file paths."""

    def test_basic_path(self, tmp_settings):
        path = task_state_path("myslug", 0, 1, tmp_settings)
        assert path.name == "myslug_p0_t1_state.json"
        assert path.parent == tmp_settings.reviews_dir

    def test_different_phase_task(self, tmp_settings):
        path = task_state_path("proj", 2, 5, tmp_settings)
        assert path.name == "proj_p2_t5_state.json"

    def test_paths_are_unique(self, tmp_settings):
        p1 = task_state_path("s", 0, 1, tmp_settings)
        p2 = task_state_path("s", 0, 2, tmp_settings)
        p3 = task_state_path("s", 1, 1, tmp_settings)
        assert p1 != p2 != p3


class TestTaskStateModel:
    """3.6: TaskState Pydantic model validation."""

    def test_valid_creation(self):
        ts = TaskState(slug="s", phase=0, task=1)
        assert ts.slug == "s"
        assert ts.phase == 0
        assert ts.task == 1
        assert ts.mode == Mode.CODE.value
        assert ts.current_round == 1
        assert ts.status == Status.NEEDS_REVIEW.value

    def test_rejects_invalid_mode(self):
        with pytest.raises(ValidationError):
            TaskState(slug="s", phase=0, task=1, mode="bogus")

    def test_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            TaskState(slug="s", phase=0, task=1, status="bogus")

    def test_extra_forbid_rejects_unknown_fields(self):
        with pytest.raises(ValidationError):
            TaskState(slug="s", phase=0, task=1, unknown_field="x")


class TestTaskStateManagerInit:
    """3.6: TaskStateManager init creates correct state files."""

    def test_init_creates_file(self, tmp_settings):
        path = task_state_path("tst", 0, 1, tmp_settings)
        tsm = TaskStateManager(state_path=path)
        state = tsm.init(slug="tst", phase=0, task=1, plan_file="plan.md")
        assert path.exists()
        assert state.slug == "tst"
        assert state.phase == 0
        assert state.task == 1
        assert state.plan_file == "plan.md"
        assert state.current_round == 1
        assert state.status == Status.NEEDS_REVIEW.value
        assert state.started_at != ""

    def test_init_sets_mode(self, tmp_settings):
        path = task_state_path("tst", 1, 2, tmp_settings)
        tsm = TaskStateManager(state_path=path)
        state = tsm.init(slug="tst", phase=1, task=2, plan_file="p.md")
        assert state.mode == Mode.CODE.value


class TestTaskStateManagerCRUD:
    """3.6: TaskStateManager load/save/update/record_round."""

    @pytest.fixture
    def tsm(self, tmp_settings):
        path = task_state_path("crud", 0, 1, tmp_settings)
        tsm = TaskStateManager(state_path=path)
        tsm.init(slug="crud", phase=0, task=1, plan_file="p.md")
        return tsm

    def test_load_roundtrip(self, tsm):
        loaded = tsm.load()
        assert loaded.slug == "crud"
        assert loaded.phase == 0
        assert loaded.task == 1

    def test_load_missing_raises(self, tmp_settings):
        path = tmp_settings.reviews_dir / "nonexistent_state.json"
        tsm = TaskStateManager(state_path=path)
        with pytest.raises(FileNotFoundError):
            tsm.load()

    def test_update_changes_field(self, tsm):
        updated = tsm.update(status=Status.NEEDS_RESPONSE.value)
        assert updated.status == Status.NEEDS_RESPONSE.value

    def test_update_rejects_unknown_field(self, tsm):
        with pytest.raises(ValueError, match="Unknown task state fields"):
            tsm.update(nonexistent_field="x")

    def test_save_creates_backup(self, tsm):
        tsm.update(current_round=2)
        bak = str(tsm.state_path) + ".bak"
        assert os.path.exists(bak)

    def test_record_round(self, tsm):
        tsm.record_round(
            round_num=1,
            action="review",
            outcome="fixes_required",
            verdict="FIXES_REQUIRED",
            blocker=1,
            major=0,
            minor=0,
        )
        state = tsm.load()
        assert len(state.history) == 1
        assert state.history[0]["round"] == 1
        assert state.history[0]["verdict"] == "FIXES_REQUIRED"
        assert "timestamp" in state.history[0]

    def test_record_multiple_rounds(self, tsm):
        tsm.record_round(1, "review", "fixes_required", verdict="FIXES_REQUIRED", blocker=1)
        tsm.record_round(2, "review", "approved", verdict="APPROVED")
        state = tsm.load()
        assert len(state.history) == 2
        assert state.history[0]["round"] == 1
        assert state.history[1]["round"] == 2

    def test_code_artifact_hash(self, tsm):
        tsm.update(code_artifact_hash="abc123")
        state = tsm.load()
        assert state.code_artifact_hash == "abc123"


class TestPerTaskStateIsolation:
    """3.7: Two tasks have independent state files."""

    def test_two_tasks_independent_state(self, tmp_settings):
        path1 = task_state_path("iso", 0, 1, tmp_settings)
        path2 = task_state_path("iso", 0, 2, tmp_settings)
        tsm1 = TaskStateManager(state_path=path1)
        tsm2 = TaskStateManager(state_path=path2)

        tsm1.init(slug="iso", phase=0, task=1, plan_file="p.md")
        tsm2.init(slug="iso", phase=0, task=2, plan_file="p.md")

        # Modify task 1 state
        tsm1.update(status=Status.APPROVED.value, current_round=3)

        # Task 2 should be unaffected
        state2 = tsm2.load()
        assert state2.status == Status.NEEDS_REVIEW.value
        assert state2.current_round == 1

        # Task 1 has the changes
        state1 = tsm1.load()
        assert state1.status == Status.APPROVED.value
        assert state1.current_round == 3


# ── Campaign Index Tests (v3 Task 4) ──────────────────────────────────


class TestCampaignIndexPath:
    """4.6: campaign_index_path computes correct file path."""

    def test_basic_path(self, tmp_settings):
        path = campaign_index_path("myslug", tmp_settings)
        assert path.name == "myslug_campaign.json"
        assert path.parent == tmp_settings.reviews_dir


class TestCampaignIndexModel:
    """4.6: CampaignIndex Pydantic model validation."""

    def test_valid_creation(self):
        ci = CampaignIndex(slug="s")
        assert ci.slug == "s"
        assert ci.current_phase == 0
        assert ci.current_task == 1
        assert ci.status == Status.NEEDS_REVIEW.value

    def test_rejects_invalid_mode(self):
        with pytest.raises(ValidationError):
            CampaignIndex(slug="s", mode="bogus")

    def test_extra_forbid_rejects_unknown_fields(self):
        with pytest.raises(ValidationError):
            CampaignIndex(slug="s", unknown_field="x")


class TestCampaignManagerCRUD:
    """4.6: CampaignManager load/save/init."""

    @pytest.fixture
    def cm(self, tmp_settings):
        path = campaign_index_path("crud", tmp_settings)
        cm = CampaignManager(state_path=path, settings=tmp_settings)
        cm.init(
            slug="crud",
            mode=Mode.CODE,
            plan_file="p.md",
            total_phases=2,
            tasks_per_phase={"0": 3, "1": 2},
        )
        return cm

    def test_init_creates_file(self, cm):
        assert cm.state_path.exists()
        state = cm.load()
        assert state.slug == "crud"
        assert state.total_phases == 2
        assert state.tasks_per_phase == {"0": 3, "1": 2}

    def test_load_roundtrip(self, cm):
        state = cm.load()
        assert state.current_phase == 0
        assert state.current_task == 1
        assert state.status == Status.NEEDS_REVIEW.value

    def test_load_missing_raises(self, tmp_settings):
        path = tmp_settings.reviews_dir / "nonexistent_campaign.json"
        cm = CampaignManager(state_path=path, settings=tmp_settings)
        with pytest.raises(FileNotFoundError):
            cm.load()

    def test_init_syncs_to_cli_args(self, tmp_settings):
        """D2: init() accepts current_phase/current_task from CLI args."""
        path = campaign_index_path("sync", tmp_settings)
        cm = CampaignManager(state_path=path, settings=tmp_settings)
        cm.init(
            slug="sync",
            mode=Mode.CODE,
            plan_file="p.md",
            total_phases=3,
            tasks_per_phase={"0": 2, "1": 4, "2": 3},
            current_phase=1,
            current_task=3,
        )
        state = cm.load()
        assert state.current_phase == 1
        assert state.current_task == 3

    def test_save_creates_backup(self, cm):
        cm._update(current_task=2)
        bak = str(cm.state_path) + ".bak"
        assert os.path.exists(bak)


class TestCampaignAdvanceTask:
    """4.6: advance_task with 2+ tasks and phases."""

    @pytest.fixture
    def cm(self, tmp_settings):
        path = campaign_index_path("adv", tmp_settings)
        cm = CampaignManager(state_path=path, settings=tmp_settings)
        cm.init(
            slug="adv",
            mode=Mode.CODE,
            plan_file="p.md",
            total_phases=2,
            tasks_per_phase={"0": 3, "1": 2},
        )
        return cm

    def test_advance_within_phase(self, cm, tmp_settings):
        # Create per-task state for current task
        ts_path = task_state_path("adv", 0, 1, tmp_settings)
        tsm = TaskStateManager(state_path=ts_path)
        tsm.init(slug="adv", phase=0, task=1, plan_file="p.md")

        state = cm.advance_task()
        assert state.current_phase == 0
        assert state.current_task == 2
        assert state.status == Status.NEEDS_REVIEW.value

        # Per-task state should be APPROVED
        ts = tsm.load()
        assert ts.status == Status.APPROVED.value

    def test_advance_cross_phase(self, cm, tmp_settings):
        # Advance through all 3 tasks in phase 0
        for t in range(1, 4):
            ts_path = task_state_path("adv", 0, t, tmp_settings)
            tsm = TaskStateManager(state_path=ts_path)
            tsm.init(slug="adv", phase=0, task=t, plan_file="p.md")
            cm.advance_task()

        state = cm.load()
        assert state.current_phase == 1
        assert state.current_task == 1

    def test_advance_to_complete(self, cm, tmp_settings):
        # Advance through all tasks in all phases
        for t in range(1, 4):
            ts_path = task_state_path("adv", 0, t, tmp_settings)
            tsm = TaskStateManager(state_path=ts_path)
            tsm.init(slug="adv", phase=0, task=t, plan_file="p.md")
            cm.advance_task()

        for t in range(1, 3):
            ts_path = task_state_path("adv", 1, t, tmp_settings)
            tsm = TaskStateManager(state_path=ts_path)
            tsm.init(slug="adv", phase=1, task=t, plan_file="p.md")
            cm.advance_task()

        state = cm.load()
        assert state.status == Status.COMPLETE.value

    def test_advance_without_pertask_state(self, cm):
        # advance_task should work even without per-task state file
        state = cm.advance_task()
        assert state.current_task == 2

    def test_offbyone_regression(self, tmp_settings):
        """Campaign with 5 phases, 1 task each — must complete at phase 4."""
        path = campaign_index_path("obo", tmp_settings)
        cm = CampaignManager(state_path=path, settings=tmp_settings)
        cm.init(
            slug="obo",
            mode=Mode.CODE,
            plan_file="p.md",
            total_phases=5,
            tasks_per_phase={"0": 1, "1": 1, "2": 1, "3": 1, "4": 1},
        )
        for _ in range(5):
            cm.advance_task()
        state = cm.load()
        assert state.status == Status.COMPLETE.value
