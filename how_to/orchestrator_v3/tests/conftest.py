"""Shared pytest fixtures for orchestrator_v3 tests."""

import sys
from pathlib import Path

# Ensure orchestrator_v3 is importable regardless of how pytest is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m not slow')"
    )

from orchestrator_v3.config import OrchestratorSettings
from orchestrator_v3.state import StateManager


@pytest.fixture
def tmp_settings(tmp_path):
    """OrchestratorSettings rooted in a temporary directory."""
    settings = OrchestratorSettings(repo_root=tmp_path)
    settings.reviews_dir.mkdir(parents=True, exist_ok=True)
    settings.active_plans_dir.mkdir(parents=True, exist_ok=True)
    return settings


@pytest.fixture
def tmp_state_manager(tmp_settings):
    """StateManager pointing at a temp state file."""
    state_path = tmp_settings.reviews_dir / "test_orchestrator_state.json"
    return StateManager(state_path=state_path, settings=tmp_settings)


@pytest.fixture
def complex_plan_dir(tmp_settings):
    """Create a complex plan structure: master + phases/."""
    slug = "test_slug"
    plan_dir = tmp_settings.active_plans_dir / slug
    phases_dir = plan_dir / "phases"
    phases_dir.mkdir(parents=True)

    master = plan_dir / f"{slug}_master_plan.md"
    master.write_text("# Test Master Plan\n\n## Phases Overview\n")

    phase0 = phases_dir / "phase_0_test.md"
    phase0.write_text("# Phase 0: Test\n\n### [ ] 1 Task One\n")

    return slug, plan_dir


@pytest.fixture
def simple_plan_file(tmp_settings):
    """Create a single-file simple plan."""
    slug = "simple_slug"
    plan_file = tmp_settings.active_plans_dir / f"{slug}.md"
    plan_file.write_text("# Simple Plan\n\n## Tasks\n")
    return slug, plan_file


@pytest.fixture
def tmp_research_settings(tmp_path):
    """OrchestratorSettings with research_dir rooted in a temporary directory."""
    settings = OrchestratorSettings(repo_root=tmp_path)
    settings.reviews_dir.mkdir(parents=True, exist_ok=True)
    settings.active_plans_dir.mkdir(parents=True, exist_ok=True)
    settings.research_dir.mkdir(parents=True, exist_ok=True)
    return settings


# ---------------------------------------------------------------------------
# Plan test fixtures (used by plan_tool tests in Phase 0+)
# ---------------------------------------------------------------------------


@pytest.fixture
def fixtures_dir():
    """Return the path to plan test fixtures."""
    return Path(__file__).parent / "fixtures" / "plans"


@pytest.fixture
def complex_plan_fixture(fixtures_dir):
    """Return path to the well-formed complex plan directory."""
    return fixtures_dir / "complex_wellformed"


@pytest.fixture
def simple_plan_fixture(fixtures_dir):
    """Return path to the well-formed simple plan file."""
    return fixtures_dir / "simple_wellformed" / "simple_test_plan.md"


@pytest.fixture
def malformed_plan(fixtures_dir):
    """Return dict mapping defect names to malformed plan file paths."""
    malformed_dir = fixtures_dir / "malformed"
    return {
        "missing_sections": malformed_dir / "missing_sections.md",
        "numbering_gaps": malformed_dir / "numbering_gaps.md",
        "depth_violation": malformed_dir / "depth_violation.md",
        "checked_heading": malformed_dir / "checked_heading.md",
        "mixed_defects": malformed_dir / "mixed_defects.md",
    }


@pytest.fixture
def parsed_plan(complex_plan_fixture):
    """Return raw text of the first phase file from the complex plan fixture."""
    phase_dir = complex_plan_fixture / "phases"
    first_phase = sorted(phase_dir.glob("phase_*.md"))[0]
    return first_phase.read_text()
