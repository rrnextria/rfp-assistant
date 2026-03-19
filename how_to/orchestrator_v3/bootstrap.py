"""Isolated venv bootstrap for the orchestrator.

Creates and manages ``how_to/.venv/`` so the orchestrator always runs with
its own ``pydantic`` and ``typer`` regardless of the host project's environment.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

_MIN_PYTHON = (3, 10)


def _check_python_version() -> None:
    """Raise SystemExit if the interpreter is too old."""
    if sys.version_info < _MIN_PYTHON:
        raise SystemExit(
            f"Python {_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}+ is required "
            f"(running {sys.version_info.major}.{sys.version_info.minor}).\n"
            "Hint: install Python 3.10+ (apt install python3 python3-venv) then run: ./how_to/maistro"
        )


def _requirements_hash(how_to_dir: Path) -> str:
    """SHA-256 fingerprint of requirements.txt (first 16 hex chars)."""
    req = how_to_dir / "orchestrator_v3" / "requirements.txt"
    return hashlib.sha256(req.read_bytes()).hexdigest()[:16]


def _requirements_stale(venv_dir: Path, how_to_dir: Path) -> bool:
    """True if venv was built from a different requirements.txt."""
    stamp = venv_dir / ".requirements_hash"
    if not stamp.exists():
        return True
    return stamp.read_text().strip() != _requirements_hash(how_to_dir)


def _venv_python(venv_dir: Path) -> Path:
    """Return the Python interpreter path inside *venv_dir*."""
    return venv_dir / "bin" / "python"


def _find_pip(venv_dir: Path) -> str:
    """Return the best pip executable path inside *venv_dir*.

    After ensurepip, ``bin/pip`` may not exist — only ``bin/pip3`` or
    ``bin/pipX.Y``.  This function probes all candidates and returns the
    first match, falling back to ``-m pip`` invocation via the venv
    interpreter.
    """
    bin_dir = venv_dir / "bin"
    for name in ("pip", "pip3", f"pip{sys.version_info.major}.{sys.version_info.minor}"):
        candidate = bin_dir / name
        if candidate.is_file():
            return str(candidate)
    # Last resort: use the venv python to run pip as a module
    return None


def _is_venv_healthy(venv_dir: Path) -> bool:
    """Return True if the venv's interpreter exists and can import deps."""
    py = _venv_python(venv_dir)
    if not py.is_file():
        return False
    try:
        result = subprocess.run(
            [str(py), "-c", "import pydantic; import typer"],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _create_venv(venv_dir: Path, how_to_dir: Path) -> None:
    """Create the venv and install requirements."""
    req_file = how_to_dir / "orchestrator_v3" / "requirements.txt"

    # Prefer uv if available
    uv = shutil.which("uv")
    if uv:
        print("Creating orchestrator environment (uv)...")
        subprocess.run([uv, "venv", str(venv_dir)], check=True, capture_output=True)
        print("Installing dependencies...")
        subprocess.run(
            [uv, "pip", "install", "-r", str(req_file), "--python", str(_venv_python(venv_dir))],
            check=True,
            capture_output=True,
        )
    else:
        print("Creating orchestrator environment (venv)...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
        )
        pip_path = _find_pip(venv_dir)
        if not pip_path:
            # ensurepip fallback
            print("Installing pip via ensurepip...")
            subprocess.run(
                [str(_venv_python(venv_dir)), "-m", "ensurepip", "--upgrade"],
                check=True,
                capture_output=True,
            )
            pip_path = _find_pip(venv_dir)
        print("Installing dependencies...")
        if pip_path:
            subprocess.run(
                [pip_path, "install", "-r", str(req_file)],
                check=True,
                capture_output=True,
            )
        else:
            # No pip binary found — invoke as module
            subprocess.run(
                [str(_venv_python(venv_dir)), "-m", "pip", "install", "-r", str(req_file)],
                check=True,
                capture_output=True,
            )

    # Record which requirements.txt produced this venv
    stamp = venv_dir / ".requirements_hash"
    stamp.write_text(_requirements_hash(how_to_dir))


def _remove_venv(venv_dir: Path, how_to_dir: Path) -> None:
    """Remove *venv_dir*, converting PermissionError to SystemExit."""
    try:
        shutil.rmtree(venv_dir)
    except PermissionError as exc:
        raise SystemExit(
            f"Permission denied removing orchestrator environment at {venv_dir}: {exc}\n"
            f"Hint: check directory permissions for {how_to_dir}"
        ) from exc


def ensure_venv(how_to_dir: Path) -> Path:
    """Ensure the orchestrator's isolated venv exists and is healthy.

    Returns the path to the venv's Python interpreter.  Creates the venv
    on first run, validates it on subsequent runs, and auto-recreates it
    if validation fails (missing interpreter or failed import probe).
    """
    _check_python_version()

    venv_dir = how_to_dir / ".venv"

    if venv_dir.is_dir():
        stale = _requirements_stale(venv_dir, how_to_dir)
        healthy = _is_venv_healthy(venv_dir)
        if healthy and not stale:
            return _venv_python(venv_dir)
        reason = "dependencies changed" if stale else "unhealthy"
        print(f"Existing orchestrator environment {reason}, recreating...")
        _remove_venv(venv_dir, how_to_dir)

    try:
        _create_venv(venv_dir, how_to_dir)
    except subprocess.CalledProcessError as exc:
        stderr = str(exc.stderr or b"", "utf-8") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        msg = f"Failed to create orchestrator environment: {exc}"
        if any(s in stderr for s in (
            "No module named pip", "No module named ensurepip",
            "ensurepip is not available",
        )):
            msg += "\nHint: pip is not available. Install it with: apt install python3-pip python3-venv"
        elif any(s in stderr for s in (
            "Could not find", "No matching distribution",
            "Could not fetch URL", "name resolution",
            "ConnectionError", "SSLError",
        )):
            msg += "\nHint: network may be unavailable or package version not found."
        raise SystemExit(msg) from exc
    except PermissionError as exc:
        raise SystemExit(
            f"Permission denied creating orchestrator environment at {venv_dir}: {exc}\n"
            f"Hint: check directory permissions for {how_to_dir}"
        ) from exc

    print("Orchestrator environment ready.")
    return _venv_python(venv_dir)


def reset_venv(how_to_dir: Path) -> Path:
    """Delete and recreate the orchestrator's venv from scratch.

    Returns the path to the new venv's Python interpreter.
    """
    venv_dir = how_to_dir / ".venv"
    if venv_dir.is_dir():
        print("Removing existing orchestrator environment...")
        _remove_venv(venv_dir, how_to_dir)
    return ensure_venv(how_to_dir)
