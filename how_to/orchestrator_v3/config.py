"""Core enums and Pydantic settings for orchestrator_v3."""

from __future__ import annotations

import os
import subprocess
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator


def _load_dotenv() -> None:
    """Load .env file from how_to/ directory if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


_load_dotenv()


class Status(str, Enum):
    """Review-loop lifecycle status."""

    NEEDS_REVIEW = "needs_review"
    NEEDS_RESPONSE = "needs_response"
    APPROVED = "approved"
    COMPLETE = "complete"


class Mode(str, Enum):
    """Review mode — plan review, code review, or research deliberation."""

    PLAN = "plan"
    CODE = "code"
    RESEARCH = "research"


class PlanType(str, Enum):
    """Plan structure — simple (single file) or complex (master + phases)."""

    SIMPLE = "simple"
    COMPLEX = "complex"


def detect_repo_root() -> Path:
    """Auto-detect repo root with graceful fallback to cwd.

    Tries three strategies in order:
    1. Walk up from config.py's directory looking for ``.git`` (directory
       or file, supporting worktrees and submodules).
    2. Ask ``git rev-parse --show-toplevel`` (subprocess).
    3. Fall back to ``Path.cwd()`` if git is unavailable
       (``FileNotFoundError``) or the directory is not inside a git
       repository (``CalledProcessError``).
    """
    candidate = Path(__file__).resolve().parent.parent.parent
    if (candidate / ".git").exists():
        return candidate
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (FileNotFoundError, subprocess.CalledProcessError):
        import logging

        logging.getLogger(__name__).warning(
            "detect_repo_root: git unavailable or not in a repo, falling back to cwd"
        )
        return Path.cwd()


def _env_str(key: str, default: str) -> str:
    """Read a string from environment with fallback default."""
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    """Read an int from environment with fallback default."""
    val = os.environ.get(key)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return default


class OrchestratorSettings(BaseModel):
    """Immutable configuration for an orchestrator session.

    Settings are loaded with precedence: CLI flag > .env > hardcoded default.
    The .env file at how_to/.env is loaded at module import time via
    python-dotenv (if available).

    Args:
        repo_root: Absolute path to the git repository root.
        reviews_dir: Directory for review artifacts (default: ``repo_root/reviews``).
        active_plans_dir: Directory for plan files (default: ``repo_root/active_plans``).
        default_max_rounds: Maximum review rounds before failing (default: 10).
        default_model: Codex model name (env: MAISTRO_CODEX_MODEL, default: ``gpt-5.4``).
        default_timeout: Reviewer wall-clock timeout (env: MAISTRO_TIMEOUT, default: 1800).
        default_idle_timeout: Idle timeout (env: MAISTRO_IDLE_TIMEOUT, default: 600).
        default_reasoning_effort: Codex reasoning effort (env: MAISTRO_CODEX_REASONING, default: ``high``).
        default_claude_model: Claude model for research (env: MAISTRO_CLAUDE_MODEL, default: ``opus``).
    """

    model_config = ConfigDict(frozen=True)

    repo_root: Path
    reviews_dir: Path | None = None
    active_plans_dir: Path | None = None
    research_dir: Path | None = None
    default_max_rounds: int = 10
    default_model: str = _env_str("MAISTRO_CODEX_MODEL", "gpt-5.4")
    default_timeout: int = _env_int("MAISTRO_TIMEOUT", 1800)
    default_idle_timeout: int = _env_int("MAISTRO_IDLE_TIMEOUT", 600)
    default_reasoning_effort: str = _env_str("MAISTRO_CODEX_REASONING", "high")
    default_claude_model: str = _env_str("MAISTRO_CLAUDE_MODEL", "opus")

    @model_validator(mode="after")
    def _set_derived_paths(self) -> "OrchestratorSettings":
        if self.reviews_dir is None:
            object.__setattr__(self, "reviews_dir", self.repo_root / "reviews")
        if self.active_plans_dir is None:
            object.__setattr__(
                self, "active_plans_dir", self.repo_root / "active_plans"
            )
        if self.research_dir is None:
            object.__setattr__(
                self, "research_dir", self.repo_root / "research"
            )
        return self


def get_settings() -> OrchestratorSettings:
    """Convenience: create settings with auto-detected repo root."""
    return OrchestratorSettings(repo_root=detect_repo_root())
