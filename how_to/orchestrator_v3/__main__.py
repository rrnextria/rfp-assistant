"""Entry point for ``python -m orchestrator_v3``.

Before importing the Typer CLI (which requires pydantic/typer), this module
bootstraps an isolated venv at ``how_to/.venv/`` and re-execs into it.
Only stdlib imports are used before the venv is active.
"""

import os
import sys
from pathlib import Path


def _in_venv(how_to_dir: Path) -> bool:
    """Return True if the current interpreter is running inside how_to/.venv/."""
    try:
        venv = (how_to_dir / ".venv").resolve()
        # sys.prefix points to the venv root when active (unlike sys.executable
        # which may resolve through symlinks to the base interpreter)
        prefix = Path(sys.prefix).resolve()
        return prefix == venv or str(prefix).startswith(str(venv) + os.sep)
    except (OSError, ValueError):
        return False


def _bootstrap() -> None:
    """Bootstrap gate: ensure we're running inside the isolated venv."""
    # Locate how_to/ — this file is at how_to/orchestrator_v3/__main__.py
    how_to_dir = Path(__file__).resolve().parent.parent

    # Handle --setup-env and --reset-env as top-level flags only
    # (check sys.argv[1] so subcommand arguments are never hijacked)
    first_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if first_arg == "--setup-env":
        from .bootstrap import ensure_venv
        ensure_venv(how_to_dir)
        print("Environment setup complete.")
        sys.exit(0)

    if first_arg == "--reset-env":
        from .bootstrap import reset_venv
        reset_venv(how_to_dir)
        print("Environment reset complete.")
        sys.exit(0)

    # If already inside the venv, proceed to the CLI app
    if _in_venv(how_to_dir):
        from .cli import app
        app()
        return

    # Not in venv — bootstrap and re-exec
    from .bootstrap import ensure_venv
    venv_python = ensure_venv(how_to_dir)
    print("Tip: Use './how_to/maistro <command>' for all future invocations.")

    # Preserve PYTHONPATH so the orchestrator module is findable
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    if str(how_to_dir) not in pythonpath:
        env["PYTHONPATH"] = str(how_to_dir) + (os.pathsep + pythonpath if pythonpath else "")

    # Re-exec as module invocation so relative imports work
    args = [str(venv_python), "-m", "orchestrator_v3"] + sys.argv[1:]
    os.execve(str(venv_python), args, env)


if __name__ == "__main__":
    _bootstrap()
