"""Environment checks for orchestrator_v3.

Provides fast startup checks (CLI tools, directories, repo root) and
extended diagnostics (Python version, package imports, venv state) for
the ``doctor`` command.

Startup checks use only ``shutil.which()`` and ``Path.exists()`` /
``Path.is_dir()`` — no subprocess calls.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EnvCheckResult:
    """Result of a single environment check."""

    name: str
    status: str  # "PASS", "WARN", "FAIL"
    message: str
    fix_hint: str = ""


def check_cli_tools(needed: list[str]) -> list[EnvCheckResult]:
    """Check that required CLI tools are on PATH.

    Uses ``shutil.which()`` — no subprocess calls.
    """
    results: list[EnvCheckResult] = []
    hints = {
        "claude": "Install with: npm install -g @anthropic-ai/claude-code",
        "codex": "Install with: npm install -g @openai/codex",
    }
    for tool in needed:
        path = shutil.which(tool)
        if path:
            results.append(EnvCheckResult(
                name=f"cli:{tool}",
                status="PASS",
                message=f"{tool} found at {path}",
            ))
        else:
            results.append(EnvCheckResult(
                name=f"cli:{tool}",
                status="FAIL",
                message=f"{tool} not found on PATH",
                fix_hint=hints.get(tool, f"Install {tool} and add it to PATH"),
            ))
    return results


def check_directories(repo_root: Path) -> list[EnvCheckResult]:
    """Check that expected directories exist.

    Uses ``Path.is_dir()`` — no subprocess calls.
    """
    results: list[EnvCheckResult] = []
    for dirname in ("active_plans", "reviews", "research", "maistro"):
        dirpath = repo_root / dirname
        if dirpath.is_dir():
            results.append(EnvCheckResult(
                name=f"dir:{dirname}",
                status="PASS",
                message=f"{dirname}/ exists",
            ))
        else:
            results.append(EnvCheckResult(
                name=f"dir:{dirname}",
                status="WARN",
                message=f"{dirname}/ not found",
                fix_hint=f"mkdir -p {dirpath}",
            ))
    return results


def _find_repo_root() -> Path | None:
    """Walk up from cwd looking for a ``.git`` entry (dir or file).

    Returns the repo root ``Path`` or ``None`` if not inside a repo.
    Uses ``Path.exists()`` so that git worktrees and submodules (where
    ``.git`` is a file, not a directory) are correctly detected.
    """
    cwd = Path.cwd()
    if (cwd / ".git").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / ".git").exists():
            return parent
    return None


def check_repo_root() -> EnvCheckResult:
    """Check that the current directory is inside a git repo.

    Uses ``Path.exists()`` — no subprocess calls.  Detects both regular
    repositories (``.git/`` directory) and worktrees/submodules (``.git``
    file).
    """
    root = _find_repo_root()
    if root is not None:
        cwd = Path.cwd()
        if root == cwd:
            return EnvCheckResult(
                name="repo_root",
                status="PASS",
                message="Git repository detected",
            )
        return EnvCheckResult(
            name="repo_root",
            status="PASS",
            message=f"Git repository detected at {root}",
        )
    return EnvCheckResult(
        name="repo_root",
        status="FAIL",
        message="Not inside a git repository",
        fix_hint="Ask the user: run git init, clone an existing repo, or cd to the right directory?",
    )


def check_python_version() -> EnvCheckResult:
    """Check Python version (doctor-only, not startup)."""
    ver = sys.version_info
    if ver >= (3, 10):
        return EnvCheckResult(
            name="python_version",
            status="PASS",
            message=f"Python {ver.major}.{ver.minor}.{ver.micro}",
        )
    return EnvCheckResult(
        name="python_version",
        status="WARN",
        message=f"Python {ver.major}.{ver.minor}.{ver.micro} (3.10+ recommended)",
        fix_hint="Install Python 3.10 or later",
    )


def check_required_packages() -> list[EnvCheckResult]:
    """Check that required packages can be imported (doctor-only)."""
    results: list[EnvCheckResult] = []
    for pkg in ("pydantic", "typer"):
        try:
            importlib.import_module(pkg)
            results.append(EnvCheckResult(
                name=f"pkg:{pkg}",
                status="PASS",
                message=f"{pkg} importable",
            ))
        except ImportError:
            results.append(EnvCheckResult(
                name=f"pkg:{pkg}",
                status="FAIL",
                message=f"{pkg} not importable",
                fix_hint=f"pip install {pkg}",
            ))
    return results


def check_venv() -> EnvCheckResult:
    """Check orchestrator venv health (doctor-only)."""
    how_to_dir = Path(__file__).resolve().parent.parent
    venv_dir = how_to_dir / ".venv"
    if not venv_dir.is_dir():
        return EnvCheckResult(
            name="venv",
            status="WARN",
            message="Orchestrator venv not found",
            fix_hint="Run: python -m orchestrator_v3 --setup-env",
        )
    venv_python = venv_dir / "bin" / "python"
    if not venv_python.is_file():
        return EnvCheckResult(
            name="venv",
            status="WARN",
            message="Venv exists but python binary missing",
            fix_hint="Run: python -m orchestrator_v3 --reset-env",
        )
    try:
        result = subprocess.run(
            [str(venv_python), "-c", "import pydantic; import typer"],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            return EnvCheckResult(
                name="venv",
                status="PASS",
                message=f"Orchestrator venv healthy at {venv_dir}",
            )
        return EnvCheckResult(
            name="venv",
            status="WARN",
            message="Venv exists but import probe failed",
            fix_hint="Run: python -m orchestrator_v3 --reset-env",
        )
    except (subprocess.TimeoutExpired, OSError):
        return EnvCheckResult(
            name="venv",
            status="WARN",
            message="Venv exists but probe timed out or failed",
            fix_hint="Run: python -m orchestrator_v3 --reset-env",
        )


# Command → required CLI tools mapping
_COMMAND_TOOLS: dict[str, list[str]] = {
    "plan": ["codex"],
    "code": ["codex"],
    "research": ["claude", "codex"],
    "postmortem": ["codex"],
}


def run_env_checks(command: str) -> list[EnvCheckResult]:
    """Run environment checks relevant to the given command.

    Returns a list of check results. The caller should abort on any FAIL.
    Directory checks use the detected repo root (not cwd) so that running
    from a subdirectory produces correct paths.
    """
    results: list[EnvCheckResult] = []
    results.append(check_repo_root())
    needed = _COMMAND_TOOLS.get(command, [])
    if needed:
        results.extend(check_cli_tools(needed))
    repo_root = _find_repo_root() or Path.cwd()
    results.extend(check_directories(repo_root))
    return results
