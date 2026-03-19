"""Reviewer strategy abstraction for orchestrator_v3.

Provides a ``ReviewerBase`` protocol with two concrete implementations:
``CodexReviewer`` for production use (invokes ``codex exec`` via subprocess)
and ``MockReviewer`` for deterministic testing (copies pre-written review files).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ReviewerBase(Protocol):
    """Protocol for reviewer implementations."""

    def run_review(
        self, prompt: str, review_file: Path, log_file: Path
    ) -> bool:
        """Run a review and return True on success, False on failure."""
        ...


class CodexReviewer:
    """Invokes ``codex exec`` via subprocess with tee to log file."""

    def __init__(
        self, model: str = "gpt-5.4", timeout: int = 600,
        idle_timeout: int = 600,
        reasoning_effort: str = "high",
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.reasoning_effort = reasoning_effort
        self.proc: subprocess.Popen | None = None

    def run_review(
        self, prompt: str, review_file: Path, log_file: Path
    ) -> bool:
        """Invoke ``codex exec`` with the given prompt; tee output to log file.

        Args:
            prompt: The full reviewer prompt text.
            review_file: Path where Codex writes the review artifact.
            log_file: Path for the raw Codex stdout/stderr log.

        Returns:
            True if Codex exits successfully, False on timeout or error.
        """
        cmd = [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "-m",
            self.model,
            "-c",
            f'reasoning.effort="{self.reasoning_effort}"',
            prompt,
        ]
        log_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self.proc = proc

            # Tee stdout to both sys.stdout and log file in a background
            # thread.  Track the timestamp of last output so the main
            # thread can enforce an *activity-based* idle timeout instead
            # of a fixed wall-clock timeout.  This allows long-running
            # but actively-producing Codex sessions to complete while
            # still killing truly stalled processes.
            last_activity = time.monotonic()
            activity_lock = threading.Lock()
            captured = bytearray()

            def _tee():
                nonlocal last_activity
                with open(log_file, "wb") as lf:
                    while True:
                        chunk = proc.stdout.read1(4096)
                        if not chunk:
                            break
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                        lf.write(chunk)
                        captured.extend(chunk)
                        with activity_lock:
                            last_activity = time.monotonic()

            tee_thread = threading.Thread(target=_tee, daemon=True)
            tee_thread.start()

            # Poll for completion using both wall-clock and idle timeouts.
            start_time = time.monotonic()
            while tee_thread.is_alive():
                tee_thread.join(timeout=5)
                elapsed = time.monotonic() - start_time
                with activity_lock:
                    idle = time.monotonic() - last_activity
                if idle > self.idle_timeout:
                    logger.warning(
                        "Codex idle for %d seconds (no output), killing "
                        "(idle_timeout=%d)",
                        int(idle), self.idle_timeout,
                    )
                    proc.kill()
                    proc.wait()
                    return False
                if elapsed > self.timeout:
                    logger.warning(
                        "Codex exceeded wall-clock timeout of %d seconds "
                        "(still active, last output %ds ago)",
                        self.timeout, int(idle),
                    )
                    proc.kill()
                    proc.wait()
                    return False

            proc.wait(timeout=10)

            elapsed = time.monotonic() - start_time

            if proc.returncode != 0:
                logger.warning(
                    "Codex exited with code %d", proc.returncode
                )
                return False

            # Empty-output detection: 0 bytes + fast exit → likely silent failure
            if len(captured) == 0 and elapsed < 30:
                logger.warning(
                    "Codex produced 0 bytes of output in %.1fs (exit code %d) "
                    "— treating as failure",
                    elapsed, proc.returncode,
                )
                return False

            return True
        except subprocess.TimeoutExpired:
            logger.warning(
                "Codex timed out after %d seconds", self.timeout
            )
            proc.kill()
            proc.wait()
            return False
        except FileNotFoundError:
            logger.warning(
                "codex binary not found on PATH. "
                "Install with: npm install -g @openai/codex"
            )
            return False
        except OSError as exc:
            logger.warning("OS error invoking codex: %s", exc)
            return False
        finally:
            self.proc = None


class MockReviewer:
    """Copies pre-written review files from a mock directory."""

    def __init__(self, mock_dir: Path) -> None:
        self.mock_dir = mock_dir

    def run_review(
        self, prompt: str, review_file: Path, log_file: Path
    ) -> bool:
        """Copy the pre-written mock review for the matching round number.

        Args:
            prompt: Ignored (mock does not invoke any model).
            review_file: Destination path for the mock review.
            log_file: Path for a log noting which mock file was copied.

        Returns:
            True if a matching mock file exists and is copied, False otherwise.
        """
        # Parse round number from review_file name
        m = re.search(r"round(\d+)\.md$", review_file.name)
        round_num = int(m.group(1)) if m else 1
        source = self.mock_dir / f"round{round_num}_review.md"

        log_file.parent.mkdir(parents=True, exist_ok=True)
        review_file.parent.mkdir(parents=True, exist_ok=True)

        if source.exists():
            shutil.copy2(source, review_file)
            log_file.write_text(
                f"[MockReviewer] Copied {source} -> {review_file}\n"
            )
            return True
        else:
            log_file.write_text(
                f"[MockReviewer] Mock file not found: {source}\n"
            )
            return False
