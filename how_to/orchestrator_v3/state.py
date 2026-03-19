"""Atomic state management for orchestrator_v3."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from orchestrator_v3.config import Mode, OrchestratorSettings, PlanType, Status


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestratorState(BaseModel):
    """Pydantic model representing the full orchestrator state.

    Serialized as JSON to ``{slug}_orchestrator_state.json`` in the reviews
    directory.  All enum fields use string values for JSON compatibility.
    """

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    plan_slug: str
    mode: Mode
    plan_file: str
    plan_type: PlanType
    current_phase: int = 0
    current_task: int = 1
    current_round: int = 1
    status: Status = Status.NEEDS_REVIEW
    started_at: str = ""
    last_updated: str = ""
    total_phases: int = 1
    tasks_per_phase: dict[str, int] = Field(default_factory=dict)
    current_stage: int = 0
    total_stages: int = 1
    stage_files: list[str] = Field(default_factory=list)
    code_artifact_hash: str | None = None
    history: list[dict] = Field(default_factory=list)


class StateManager:
    """Manages atomic persistence of :class:`OrchestratorState`.

    State is written atomically via tempfile + ``os.replace`` to prevent
    corruption.  A ``.bak`` copy is kept before each write.

    Args:
        state_path: Path to the JSON state file.
        settings: Orchestrator settings (for derived paths).
    """

    def __init__(self, state_path: Path, settings: OrchestratorSettings) -> None:
        self.state_path = state_path
        self.settings = settings

    def load(self) -> OrchestratorState:
        """Load and validate state from disk.

        Raises:
            FileNotFoundError: If the state file does not exist.
        """
        if not self.state_path.exists():
            raise FileNotFoundError(
                f"State file not found: {self.state_path}"
            )
        return OrchestratorState.model_validate_json(
            self.state_path.read_text()
        )

    def save(self, state: OrchestratorState) -> OrchestratorState:
        """Persist state atomically. Returns the saved state (with updated last_updated)."""
        os.makedirs(self.state_path.parent, exist_ok=True)

        # Update timestamp
        state = state.model_copy(update={"last_updated": _now_iso()})

        # Backup existing state
        if self.state_path.exists():
            shutil.copy2(self.state_path, str(self.state_path) + ".bak")

        # Atomic write: tempfile in same dir + os.replace
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            dir=self.state_path.parent,
            suffix=".tmp",
            delete=False,
        )
        try:
            fd.write(state.model_dump_json(indent=2))
            fd.close()
            os.replace(fd.name, self.state_path)
        except BaseException:
            fd.close()
            try:
                os.unlink(fd.name)
            except OSError:
                pass
            raise
        return state

    def init(
        self,
        plan_slug: str,
        mode: Mode,
        plan_file: str,
        plan_type: PlanType,
        total_phases: int = 1,
        tasks_per_phase: dict[str, int] | None = None,
        total_stages: int = 1,
        stage_files: list[str] | None = None,
        current_stage: int = 0,
    ) -> OrchestratorState:
        """Create and persist a fresh state file for a new review session."""
        now = _now_iso()
        state = OrchestratorState(
            plan_slug=plan_slug,
            mode=mode,
            plan_file=plan_file,
            plan_type=plan_type,
            current_phase=0,
            current_task=1,
            current_round=1,
            current_stage=current_stage,
            total_stages=total_stages,
            stage_files=stage_files or [],
            code_artifact_hash=None,
            status=Status.NEEDS_REVIEW,
            started_at=now,
            last_updated=now,
            total_phases=total_phases,
            tasks_per_phase=tasks_per_phase or {},
            history=[],
        )
        return self.save(state)

    def update(self, **kwargs) -> OrchestratorState:
        """Update specific fields on the current state and persist.

        Raises:
            ValueError: If any key in *kwargs* is not a valid state field.
        """
        state = self.load()
        # Reject unknown fields explicitly
        valid_fields = set(OrchestratorState.model_fields.keys())
        unknown = set(kwargs.keys()) - valid_fields
        if unknown:
            raise ValueError(
                f"Unknown state fields: {unknown}. "
                f"Valid fields: {sorted(valid_fields)}"
            )
        new_state = state.model_copy(update=kwargs)
        # Revalidate through Pydantic
        validated = OrchestratorState.model_validate(new_state.model_dump())
        return self.save(validated)

    def advance_task(self) -> OrchestratorState:
        """Advance to the next task or phase.

        Completion semantics: when the last task of the last phase is
        complete, ``status`` is set to COMPLETE but ``current_phase``
        remains at the last valid phase index (not incremented past it).
        This keeps the state pointing at the final work item for
        display/history purposes.
        """
        state = self.load()
        next_task = state.current_task + 1
        phase_key = str(state.current_phase)
        max_tasks = state.tasks_per_phase.get(phase_key, 1)

        if next_task > max_tasks:
            # Advance to next phase
            next_phase = state.current_phase + 1
            if next_phase >= state.total_phases:
                # All phases done — keep current_phase at last valid index
                return self.update(status=Status.COMPLETE)
            return self.update(
                current_phase=next_phase,
                current_task=1,
                current_round=1,
                status=Status.NEEDS_REVIEW,
            )
        else:
            return self.update(
                current_task=next_task,
                current_round=1,
                status=Status.NEEDS_REVIEW,
            )

    def record_round(
        self,
        round_num: int,
        action: str,
        outcome: str,
        artifact_path: str | None = None,
        verdict: str | None = None,
        blocker: int = 0,
        major: int = 0,
        minor: int = 0,
        stage_label: str | None = None,
    ) -> OrchestratorState:
        """Append a review-round entry to the history list and persist."""
        state = self.load()
        entry = {
            "round": round_num,
            "action": action,
            "outcome": outcome,
            "artifact": artifact_path,
            "verdict": verdict,
            "blocker": blocker,
            "major": major,
            "minor": minor,
            "stage_label": stage_label,
            "timestamp": _now_iso(),
        }
        new_history = state.history + [entry]
        return self.update(history=new_history)


# ── Per-Task State (v3 addition) ──────────────────────────────────────


def task_state_path(
    slug: str, phase: int, task: int, settings: OrchestratorSettings
) -> Path:
    """Compute the per-task state file path.

    Returns ``reviews/{slug}_p{phase}_t{task}_state.json``.
    """
    return settings.reviews_dir / f"{slug}_p{phase}_t{task}_state.json"


class TaskState(BaseModel):
    """Per-task state for code-mode reviews.

    Each ``(slug, phase, task)`` tuple gets its own state file, isolating
    round tracking from campaign-level progress.
    """

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    slug: str
    phase: int
    task: int
    mode: Mode = Mode.CODE
    current_round: int = 1
    status: Status = Status.NEEDS_REVIEW
    plan_file: str = ""
    code_artifact_hash: str | None = None
    started_at: str = ""
    last_updated: str = ""
    history: list[dict] = Field(default_factory=list)


class TaskStateManager:
    """Manages atomic persistence of :class:`TaskState`.

    Same atomic write semantics as :class:`StateManager` (tempfile +
    ``os.replace`` + ``.bak``), but scoped to a single ``(slug, phase, task)``.
    """

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    def load(self) -> TaskState:
        """Load and validate task state from disk."""
        if not self.state_path.exists():
            raise FileNotFoundError(
                f"Task state file not found: {self.state_path}"
            )
        return TaskState.model_validate_json(self.state_path.read_text())

    def save(self, state: TaskState) -> TaskState:
        """Persist task state atomically."""
        os.makedirs(self.state_path.parent, exist_ok=True)
        state = state.model_copy(update={"last_updated": _now_iso()})

        if self.state_path.exists():
            shutil.copy2(self.state_path, str(self.state_path) + ".bak")

        fd = tempfile.NamedTemporaryFile(
            mode="w",
            dir=self.state_path.parent,
            suffix=".tmp",
            delete=False,
        )
        try:
            fd.write(state.model_dump_json(indent=2))
            fd.close()
            os.replace(fd.name, self.state_path)
        except BaseException:
            fd.close()
            try:
                os.unlink(fd.name)
            except OSError:
                pass
            raise
        return state

    def init(
        self,
        slug: str,
        phase: int,
        task: int,
        plan_file: str,
        mode: Mode = Mode.CODE,
    ) -> TaskState:
        """Create and persist a fresh per-task state file."""
        now = _now_iso()
        state = TaskState(
            slug=slug,
            phase=phase,
            task=task,
            mode=mode,
            plan_file=plan_file,
            current_round=1,
            status=Status.NEEDS_REVIEW,
            started_at=now,
            last_updated=now,
            history=[],
        )
        return self.save(state)

    def update(self, **kwargs) -> TaskState:
        """Update specific fields and persist."""
        state = self.load()
        valid_fields = set(TaskState.model_fields.keys())
        unknown = set(kwargs.keys()) - valid_fields
        if unknown:
            raise ValueError(
                f"Unknown task state fields: {unknown}. "
                f"Valid fields: {sorted(valid_fields)}"
            )
        new_state = state.model_copy(update=kwargs)
        validated = TaskState.model_validate(new_state.model_dump())
        return self.save(validated)

    def record_round(
        self,
        round_num: int,
        action: str,
        outcome: str,
        artifact_path: str | None = None,
        verdict: str | None = None,
        blocker: int = 0,
        major: int = 0,
        minor: int = 0,
        stage_label: str | None = None,
    ) -> TaskState:
        """Append a review-round entry to the history list and persist."""
        state = self.load()
        entry = {
            "round": round_num,
            "action": action,
            "outcome": outcome,
            "artifact": artifact_path,
            "verdict": verdict,
            "blocker": blocker,
            "major": major,
            "minor": minor,
            "stage_label": stage_label,
            "timestamp": _now_iso(),
        }
        new_history = state.history + [entry]
        return self.update(history=new_history)


# ── Campaign Index (v3 addition) ──────────────────────────────────────


def campaign_index_path(
    slug: str, settings: OrchestratorSettings
) -> Path:
    """Compute the campaign index file path.

    Returns ``reviews/{slug}_campaign.json``.
    """
    return settings.reviews_dir / f"{slug}_campaign.json"


class CampaignIndex(BaseModel):
    """Campaign-level index tracking overall code-mode progress.

    Tracks which ``(phase, task)`` the campaign is currently on, while
    per-task state files hold round-level detail.
    """

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    slug: str
    mode: Mode = Mode.CODE
    plan_file: str = ""
    current_phase: int = 0
    current_task: int = 1
    total_phases: int = 1
    tasks_per_phase: dict[str, int] = Field(default_factory=dict)
    status: Status = Status.NEEDS_REVIEW
    started_at: str = ""
    last_updated: str = ""


class CampaignManager:
    """Manages atomic persistence of :class:`CampaignIndex`.

    Same atomic write semantics as other managers (tempfile +
    ``os.replace`` + ``.bak``).

    Args:
        state_path: Path to the campaign JSON file.
        settings: Orchestrator settings (for derived paths).
    """

    def __init__(self, state_path: Path, settings: OrchestratorSettings) -> None:
        self.state_path = state_path
        self.settings = settings

    def load(self) -> CampaignIndex:
        """Load and validate campaign index from disk."""
        if not self.state_path.exists():
            raise FileNotFoundError(
                f"Campaign index not found: {self.state_path}"
            )
        return CampaignIndex.model_validate_json(self.state_path.read_text())

    def save(self, state: CampaignIndex) -> CampaignIndex:
        """Persist campaign index atomically."""
        os.makedirs(self.state_path.parent, exist_ok=True)
        state = state.model_copy(update={"last_updated": _now_iso()})

        if self.state_path.exists():
            shutil.copy2(self.state_path, str(self.state_path) + ".bak")

        fd = tempfile.NamedTemporaryFile(
            mode="w",
            dir=self.state_path.parent,
            suffix=".tmp",
            delete=False,
        )
        try:
            fd.write(state.model_dump_json(indent=2))
            fd.close()
            os.replace(fd.name, self.state_path)
        except BaseException:
            fd.close()
            try:
                os.unlink(fd.name)
            except OSError:
                pass
            raise
        return state

    def init(
        self,
        slug: str,
        mode: Mode,
        plan_file: str,
        total_phases: int = 1,
        tasks_per_phase: dict[str, int] | None = None,
        current_phase: int = 0,
        current_task: int = 1,
    ) -> CampaignIndex:
        """Create and persist a fresh campaign index.

        Args:
            current_phase: Initial phase pointer (synced from CLI args).
            current_task: Initial task pointer (synced from CLI args).
        """
        now = _now_iso()
        state = CampaignIndex(
            slug=slug,
            mode=mode,
            plan_file=plan_file,
            current_phase=current_phase,
            current_task=current_task,
            total_phases=total_phases,
            tasks_per_phase=tasks_per_phase or {},
            status=Status.NEEDS_REVIEW,
            started_at=now,
            last_updated=now,
        )
        return self.save(state)

    def advance_task(
        self,
        expected_phase: int | None = None,
        expected_task: int | None = None,
    ) -> CampaignIndex:
        """Advance to the next task or phase in the campaign.

        Also marks the current per-task state as APPROVED. Atomicity
        guarantee: both temp files are prepared first, then replaced in
        sequence (per-task first, campaign second). If the campaign
        replace fails after per-task is committed, the per-task state is
        rolled back from its ``.bak`` copy, ensuring neither write is
        committed on error.

        Completion semantics: when the last task of the last phase is
        complete, ``status`` is set to COMPLETE and ``current_phase``
        remains at the last valid index.

        Args:
            expected_phase: If provided, raises ValueError if campaign is not at this phase.
            expected_task: If provided, raises ValueError if campaign is not at this task.

        Raises:
            ValueError: If expected_phase or expected_task mismatch the current campaign pointer.
        """
        state = self.load()

        # Validate campaign pointer matches expectations
        if expected_phase is not None and state.current_phase != expected_phase:
            raise ValueError(
                f"Campaign phase mismatch: expected {expected_phase}, "
                f"but campaign is at phase {state.current_phase}"
            )
        if expected_task is not None and state.current_task != expected_task:
            raise ValueError(
                f"Campaign task mismatch: expected {expected_task}, "
                f"but campaign is at task {state.current_task}"
            )

        # Prepare per-task state update (write temp file first)
        ts_path = task_state_path(
            state.slug, state.current_phase, state.current_task,
            self.settings,
        )
        ts_temp_fd = None
        if ts_path.exists():
            tsm = TaskStateManager(state_path=ts_path)
            ts_state = tsm.load()
            ts_state = ts_state.model_copy(update={
                "status": Status.APPROVED,
                "last_updated": _now_iso(),
            })
            # Write temp file (but don't replace yet)
            os.makedirs(ts_path.parent, exist_ok=True)
            ts_temp_fd = tempfile.NamedTemporaryFile(
                mode="w",
                dir=ts_path.parent,
                suffix=".tmp",
                delete=False,
            )
            ts_temp_fd.write(ts_state.model_dump_json(indent=2))
            ts_temp_fd.close()

        # Compute campaign advance
        next_task = state.current_task + 1
        phase_key = str(state.current_phase)
        max_tasks = state.tasks_per_phase.get(phase_key, 1)

        if next_task > max_tasks:
            next_phase = state.current_phase + 1
            if next_phase >= state.total_phases:
                new_state = state.model_copy(update={
                    "status": Status.COMPLETE,
                    "last_updated": _now_iso(),
                })
            else:
                new_state = state.model_copy(update={
                    "current_phase": next_phase,
                    "current_task": 1,
                    "status": Status.NEEDS_REVIEW,
                    "last_updated": _now_iso(),
                })
        else:
            new_state = state.model_copy(update={
                "current_task": next_task,
                "status": Status.NEEDS_REVIEW,
                "last_updated": _now_iso(),
            })

        # Prepare campaign index temp file
        if self.state_path.exists():
            shutil.copy2(self.state_path, str(self.state_path) + ".bak")

        campaign_temp_fd = tempfile.NamedTemporaryFile(
            mode="w",
            dir=self.state_path.parent,
            suffix=".tmp",
            delete=False,
        )
        campaign_temp_fd.write(new_state.model_dump_json(indent=2))
        campaign_temp_fd.close()

        # Replace both files with rollback on partial failure
        ts_bak_path = str(ts_path) + ".bak" if ts_temp_fd is not None else None
        ts_committed = False
        try:
            if ts_temp_fd is not None:
                if ts_path.exists():
                    shutil.copy2(ts_path, ts_bak_path)
                os.replace(ts_temp_fd.name, ts_path)
                ts_committed = True
            os.replace(campaign_temp_fd.name, self.state_path)
        except BaseException:
            # Roll back per-task state from .bak if it was already committed
            if ts_committed and ts_bak_path and os.path.exists(ts_bak_path):
                try:
                    os.replace(ts_bak_path, ts_path)
                except OSError:
                    pass
            # Clean up any remaining temp files
            if ts_temp_fd is not None:
                try:
                    os.unlink(ts_temp_fd.name)
                except OSError:
                    pass
            try:
                os.unlink(campaign_temp_fd.name)
            except OSError:
                pass
            raise

        return new_state

    def _update(self, **kwargs) -> CampaignIndex:
        """Update specific fields and persist."""
        state = self.load()
        new_state = state.model_copy(update=kwargs)
        validated = CampaignIndex.model_validate(new_state.model_dump())
        return self.save(validated)
