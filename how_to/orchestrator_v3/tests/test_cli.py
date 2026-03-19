"""CLI tests for orchestrator_v3 using Typer CliRunner."""

import json
import os

import pytest
from typer.testing import CliRunner

from orchestrator_v3.cli import app
from orchestrator_v3.config import Mode, OrchestratorSettings, PlanType, Status
from orchestrator_v3.state import StateManager

runner = CliRunner()


# ── Test 4.1: plan --help ─────────────────────────────────────────────

class TestPlanHelp:
    def test_plan_help_exits_0(self):
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "plan_file" in result.output.lower() or "PLAN_FILE" in result.output
        for flag in ("--resume", "--dry-run", "--max-rounds", "--model", "--mock-reviewer"):
            assert flag in result.output


# ── Test 4.2: code --help ─────────────────────────────────────────────

class TestCodeHelp:
    def test_code_help_exits_0(self):
        result = runner.invoke(app, ["code", "--help"])
        assert result.exit_code == 0
        for arg in ("slug", "phase", "task"):
            assert arg in result.output.lower()
        for flag in ("--resume", "--dry-run", "--max-rounds", "--model", "--mock-reviewer"):
            assert flag in result.output


# ── Test 4.3: status with existing state ──────────────────────────────

class TestStatusExisting:
    def test_status_shows_state(self, tmp_path, monkeypatch):
        slug = "test_cli_slug"
        settings = OrchestratorSettings(repo_root=tmp_path)
        settings.reviews_dir.mkdir(parents=True, exist_ok=True)
        sm = StateManager(
            state_path=settings.reviews_dir / f"{slug}_orchestrator_state.json",
            settings=settings,
        )
        sm.init(
            plan_slug=slug,
            mode=Mode.CODE,
            plan_file="plan.md",
            plan_type=PlanType.SIMPLE,
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")
        result = runner.invoke(app, ["status", slug])
        assert result.exit_code == 0
        assert slug in result.output
        assert "Phase" in result.output
        assert "Task" in result.output


# ── Test 4.4: status with missing state ───────────────────────────────

class TestStatusMissing:
    def test_status_missing_slug_exits_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reviews").mkdir()
        result = runner.invoke(app, ["status", "nonexistent_slug"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ── Test 4.5: info with existing state ────────────────────────────────

class TestInfoExisting:
    def test_info_shows_details(self, tmp_path, monkeypatch):
        slug = "info_slug"
        settings = OrchestratorSettings(repo_root=tmp_path)
        settings.reviews_dir.mkdir(parents=True, exist_ok=True)
        sm = StateManager(
            state_path=settings.reviews_dir / f"{slug}_orchestrator_state.json",
            settings=settings,
        )
        sm.init(
            plan_slug=slug,
            mode=Mode.CODE,
            plan_file="plan.md",
            plan_type=PlanType.SIMPLE,
            total_phases=2,
            tasks_per_phase={"0": 3, "1": 2},
        )
        sm.update(current_phase=1, current_task=1, current_round=3, status=Status.NEEDS_RESPONSE)

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")
        result = runner.invoke(app, ["info", slug])
        assert result.exit_code == 0
        assert slug in result.output
        assert "Mode:" in result.output
        assert "Current:" in result.output
        assert "Status:" in result.output
        assert "Progress:" in result.output
        assert "Phase 0:" in result.output


# ── Test 4.6: validate with valid state ───────────────────────────────

class TestValidateOK:
    def test_validate_ok(self, tmp_path, monkeypatch):
        slug = "valid_slug"
        settings = OrchestratorSettings(repo_root=tmp_path)
        settings.reviews_dir.mkdir(parents=True, exist_ok=True)
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan\n")
        sm = StateManager(
            state_path=settings.reviews_dir / f"{slug}_orchestrator_state.json",
            settings=settings,
        )
        sm.init(
            plan_slug=slug,
            mode=Mode.CODE,
            plan_file=str(plan_file),
            plan_type=PlanType.SIMPLE,
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")
        result = runner.invoke(app, ["validate", slug])
        assert result.exit_code == 0
        assert "OK" in result.output or "valid" in result.output.lower()


# ── Test 4.7: plan --dry-run ──────────────────────────────────────────

class TestPlanDryRun:
    def test_dry_run_prints_prompt(self, tmp_path, monkeypatch):
        slug = "dryrun_slug"
        plan_dir = tmp_path / "active_plans"
        plan_dir.mkdir(parents=True)
        plan_file = plan_dir / f"{slug}.md"
        plan_file.write_text("# Dry Run Plan\n\n## Tasks\n")
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        result = runner.invoke(app, [
            "plan", str(plan_file), "--dry-run", "--init", "--skip-preflight",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
