"""Tests for subprocess hardening in research.py and reviewer.py.

Validates that ClaudeRunner, CodexReviewer, and ResearchLoop._run_parallel()
correctly handle prompt delivery, empty-output detection, timeouts, large
prompt fallback, and parallel execution semantics.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from orchestrator_v3.config import OrchestratorSettings
from orchestrator_v3.research import ClaudeRunner, ResearchLoop, ResearchStateManager
from orchestrator_v3.research_prompts import ResearchPromptBuilder
from orchestrator_v3.reviewer import CodexReviewer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_proc(
    chunks: list[bytes],
    returncode: int = 0,
    wait_side_effect=None,
):
    """Build a MagicMock that behaves like subprocess.Popen.

    Args:
        chunks: Byte chunks that proc.stdout.read1() yields in order.
                The last element should be b"" to signal EOF.
        returncode: Process exit code.
        wait_side_effect: Optional side effect for proc.wait().
    """
    proc = MagicMock(spec=subprocess.Popen)
    proc.stdout = MagicMock()
    proc.stdout.read1 = MagicMock(side_effect=chunks)
    proc.returncode = returncode
    if wait_side_effect is not None:
        proc.wait = MagicMock(side_effect=wait_side_effect)
    else:
        proc.wait = MagicMock(return_value=0)
    proc.kill = MagicMock()
    proc.stdin = MagicMock()
    return proc


# ── 3.1  Prompt as positional CLI argument ────────────────────────────


class TestClaudeRunnerCommandList:
    """3.1: ClaudeRunner.run() command list includes prompt as positional arg."""

    def test_prompt_in_cmd(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        mock_proc = _make_mock_proc([b"some output", b""], returncode=0)

        with patch(
            "orchestrator_v3.research.subprocess.Popen", return_value=mock_proc
        ) as mock_popen:
            runner.run("my test prompt", output_file, log_file)

        # The prompt must appear as the last element in the command list
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        assert cmd[-1] == "my test prompt", (
            "Prompt should be the last positional argument in the command list"
        )
        assert "claude" in cmd[0]
        assert "-p" in cmd


# ── 3.2  No stdin=subprocess.PIPE for small prompts ──────────────────


class TestClaudeRunnerNoStdinPipe:
    """3.2: ClaudeRunner.run() uses stdin=DEVNULL for small prompts."""

    def test_stdin_is_devnull(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        mock_proc = _make_mock_proc([b"output", b""], returncode=0)

        with patch(
            "orchestrator_v3.research.subprocess.Popen", return_value=mock_proc
        ) as mock_popen:
            runner.run("small prompt", output_file, log_file)

        _, kwargs = mock_popen.call_args
        assert kwargs.get("stdin") == subprocess.DEVNULL, (
            "Small prompts must use stdin=subprocess.DEVNULL"
        )


# ── 3.3  Empty-output detection ──────────────────────────────────────


class TestClaudeRunnerEmptyOutput:
    """3.3: Empty output with returncode==0 and elapsed<30s returns False.

    Also verifies that the predicate does NOT fire when returncode != 0
    or elapsed >= 30s.
    """

    def test_empty_output_fast_exit_returns_false(self, tmp_path):
        """0 bytes, returncode=0, elapsed < 30s => False."""
        runner = ClaudeRunner(model="opus", timeout=60, idle_timeout=60)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        # Return b"" immediately (0 bytes of output)
        mock_proc = _make_mock_proc([b""], returncode=0)

        with patch("orchestrator_v3.research.subprocess.Popen", return_value=mock_proc):
            result = runner.run("test prompt", output_file, log_file)

        assert result is False, (
            "Empty output with fast exit and returncode=0 should return False"
        )

    def test_empty_output_nonzero_rc_returns_false_via_rc_check(self, tmp_path, caplog):
        """0 bytes, returncode!=0 => False via the returncode check, NOT empty-output.

        The function should still return False but through the non-zero
        returncode path rather than the empty-output detection path.
        """
        import logging

        runner = ClaudeRunner(model="opus", timeout=60, idle_timeout=60)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        mock_proc = _make_mock_proc([b""], returncode=1)

        with caplog.at_level(logging.WARNING), \
             patch("orchestrator_v3.research.subprocess.Popen", return_value=mock_proc):
            result = runner.run("test prompt", output_file, log_file)

        assert result is False
        # The output file should NOT exist (returncode != 0 returns before writing)
        assert not output_file.exists()
        # Verify the returncode path was taken (not the empty-output path)
        assert any("exited with code" in m for m in caplog.messages), (
            "Expected 'exited with code' log from returncode path"
        )
        assert not any("0 bytes of output" in m for m in caplog.messages), (
            "Empty-output path should NOT be reached when returncode != 0"
        )

    def test_empty_output_slow_exit_returns_true(self, tmp_path):
        """0 bytes, returncode=0, elapsed >= 30s => True (not empty-output path).

        We simulate slow elapsed time by patching time.monotonic.
        """
        runner = ClaudeRunner(model="opus", timeout=120, idle_timeout=120)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        mock_proc = _make_mock_proc([b""], returncode=0)

        call_count = 0
        base_time = 1000.0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            # Return times that make elapsed >= 30 seconds
            # The function calls monotonic at various points:
            # - last_activity init, start_time, loop checks, final elapsed calc
            # Make every call after the first few return base + 35
            if call_count <= 2:
                return base_time
            return base_time + 35.0

        with patch("orchestrator_v3.research.subprocess.Popen", return_value=mock_proc), \
             patch("orchestrator_v3.research.time.monotonic", side_effect=fake_monotonic):
            result = runner.run("test prompt", output_file, log_file)

        # With elapsed >= 30, the empty-output predicate should NOT fire,
        # so the function should return True (it writes 0 bytes to output file)
        assert result is True


# ── 3.4  Normal output returns True ──────────────────────────────────


class TestClaudeRunnerNormalOutput:
    """3.4: Subprocess returning content leads to run() returning True."""

    def test_normal_output_returns_true(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        mock_proc = _make_mock_proc(
            [b"# Analysis\nThis is the response.", b""], returncode=0
        )

        with patch("orchestrator_v3.research.subprocess.Popen", return_value=mock_proc):
            result = runner.run("test prompt", output_file, log_file)

        assert result is True
        assert output_file.exists()
        assert output_file.read_text() == "# Analysis\nThis is the response."


# ── 3.5  TimeoutExpired handling ─────────────────────────────────────


class TestClaudeRunnerTimeoutExpired:
    """3.5: subprocess.TimeoutExpired during proc.wait() kills process."""

    def test_timeout_expired_kills_and_returns_false(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        # Simulate: tee thread finishes (stdout EOF), but proc.wait(timeout=10)
        # raises TimeoutExpired on the first call only.  After kill(), the
        # subsequent wait() should succeed (process reaped).
        mock_proc = _make_mock_proc(
            [b"some output", b""],
            returncode=0,
            wait_side_effect=[
                subprocess.TimeoutExpired(cmd="claude", timeout=10),
                0,  # second call (after kill) succeeds
            ],
        )

        with patch("orchestrator_v3.research.subprocess.Popen", return_value=mock_proc):
            result = runner.run("test prompt", output_file, log_file)

        assert result is False
        mock_proc.kill.assert_called()
        # After kill, wait() should be called again (to reap the process)
        assert mock_proc.wait.call_count >= 2


# ── 3.6  ThreadPoolExecutor future timeout ───────────────────────────


class TestRunParallelFutureTimeout:
    """3.6: Future.result() timeout kills the active subprocess."""

    def test_future_timeout_kills_proc(self, tmp_path):
        settings = OrchestratorSettings(repo_root=tmp_path)
        settings.research_dir.mkdir(parents=True, exist_ok=True)
        slug = "test_timeout"
        research_dir = settings.research_dir / slug
        research_dir.mkdir(parents=True)
        (research_dir / "logs").mkdir(parents=True)

        sm = ResearchStateManager(state_path=research_dir / "state.json")
        sm.init(slug=slug, question="Test?")
        pb = ResearchPromptBuilder(question="Test?", intent="", slug=slug)

        claude = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        codex = CodexReviewer(model="gpt-5.4", timeout=30, idle_timeout=30)
        display = MagicMock()

        loop = ResearchLoop(
            state_manager=sm,
            prompt_builder=pb,
            claude_runner=claude,
            codex_runner=codex,
            display=display,
            settings=settings,
            slug=slug,
        )

        # Create mock procs that will be "active" when future times out
        mock_claude_proc = MagicMock()
        mock_codex_proc = MagicMock()

        # Mock futures that raise FutureTimeoutError
        mock_opus_future = MagicMock(spec=Future)
        mock_opus_future.result = MagicMock(side_effect=FutureTimeoutError())
        mock_codex_future = MagicMock(spec=Future)
        mock_codex_future.result = MagicMock(side_effect=FutureTimeoutError())

        mock_executor = MagicMock(spec=ThreadPoolExecutor)
        # Submit returns our mock futures in order
        mock_executor.submit = MagicMock(
            side_effect=[mock_opus_future, mock_codex_future]
        )

        # Set proc attributes so the kill path fires
        claude.proc = mock_claude_proc
        codex.proc = mock_codex_proc

        with patch("orchestrator_v3.research.ThreadPoolExecutor", return_value=mock_executor):
            opus_ok, codex_ok = loop._run_parallel(
                opus_prompt="p1", opus_artifact="a1.md", opus_log="l1.log",
                codex_prompt="p2", codex_artifact="a2.md", codex_log="l2.log",
                phase=1,
            )

        assert opus_ok is False
        assert codex_ok is False
        mock_claude_proc.kill.assert_called_once()
        mock_codex_proc.kill.assert_called_once()
        mock_executor.shutdown.assert_called_once_with(
            wait=False, cancel_futures=True,
        )


# ── 3.7  CodexReviewer empty-output detection ───────────────────────


class TestCodexReviewerEmptyOutput:
    """3.7: CodexReviewer.run_review() uses the same three-condition predicate."""

    def test_empty_output_fast_exit_returns_false(self, tmp_path):
        """0 bytes, returncode=0, elapsed < 30s => False."""
        reviewer = CodexReviewer(model="gpt-5.4", timeout=60, idle_timeout=60)
        review_file = tmp_path / "review.md"
        log_file = tmp_path / "review.log"

        mock_proc = _make_mock_proc([b""], returncode=0)

        with patch(
            "orchestrator_v3.reviewer.subprocess.Popen", return_value=mock_proc
        ):
            result = reviewer.run_review("test prompt", review_file, log_file)

        assert result is False

    def test_empty_output_nonzero_rc_returns_false(self, tmp_path, caplog):
        """0 bytes, returncode != 0 => False via returncode path, not empty-output."""
        import logging

        reviewer = CodexReviewer(model="gpt-5.4", timeout=60, idle_timeout=60)
        review_file = tmp_path / "review.md"
        log_file = tmp_path / "review.log"

        mock_proc = _make_mock_proc([b""], returncode=1)

        with caplog.at_level(logging.WARNING), \
             patch(
            "orchestrator_v3.reviewer.subprocess.Popen", return_value=mock_proc
        ):
            result = reviewer.run_review("test prompt", review_file, log_file)

        assert result is False
        # Verify the returncode path was taken (not the empty-output path)
        assert any("exited with code" in m for m in caplog.messages), (
            "Expected 'exited with code' log from returncode path"
        )
        assert not any("0 bytes of output" in m for m in caplog.messages), (
            "Empty-output path should NOT be reached when returncode != 0"
        )

    def test_empty_output_slow_exit_returns_true(self, tmp_path):
        """0 bytes, returncode=0, elapsed >= 30s => True (not empty-output path)."""
        reviewer = CodexReviewer(model="gpt-5.4", timeout=120, idle_timeout=120)
        review_file = tmp_path / "review.md"
        log_file = tmp_path / "review.log"

        mock_proc = _make_mock_proc([b""], returncode=0)

        call_count = 0
        base_time = 1000.0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return base_time
            return base_time + 35.0

        with patch("orchestrator_v3.reviewer.subprocess.Popen", return_value=mock_proc), \
             patch("orchestrator_v3.reviewer.time.monotonic", side_effect=fake_monotonic):
            result = reviewer.run_review("test prompt", review_file, log_file)

        assert result is True

    def test_normal_output_returns_true(self, tmp_path):
        """Non-empty output with returncode=0 => True."""
        reviewer = CodexReviewer(model="gpt-5.4", timeout=60, idle_timeout=60)
        review_file = tmp_path / "review.md"
        log_file = tmp_path / "review.log"

        mock_proc = _make_mock_proc([b"Review output", b""], returncode=0)

        with patch(
            "orchestrator_v3.reviewer.subprocess.Popen", return_value=mock_proc
        ):
            result = reviewer.run_review("test prompt", review_file, log_file)

        assert result is True


# ── 3.8  Large prompt uses temp-file fallback ────────────────────────


class TestClaudeRunnerLargePrompt:
    """3.8: Prompts > 100KB use temp-file stdin instead of CLI argument."""

    def test_large_prompt_uses_stdin_file(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        # Create a prompt that exceeds 100KB
        large_prompt = "x" * 110_000  # > 100,000 bytes

        mock_proc = _make_mock_proc([b"response", b""], returncode=0)

        # Capture the temp file path, its written content, and the open() reopen call
        captured_content = []
        captured_tmpfile_name = []
        captured_open_calls = []  # Track open() calls to the temp file path
        original_ntf = tempfile.NamedTemporaryFile
        import builtins
        original_open = builtins.open

        def capturing_ntf(*a, **kw):
            f = original_ntf(*a, **kw)
            captured_tmpfile_name.append(f.name)
            original_write = f.write

            def patched_write(data):
                captured_content.append(data)
                return original_write(data)

            f.write = patched_write
            return f

        def tracking_open(*a, **kw):
            result = original_open(*a, **kw)
            if captured_tmpfile_name and len(a) > 0 and str(a[0]) == captured_tmpfile_name[0]:
                captured_open_calls.append(result)
            return result

        with patch(
            "orchestrator_v3.research.subprocess.Popen", return_value=mock_proc
        ) as mock_popen, patch(
            "orchestrator_v3.research.tempfile.NamedTemporaryFile",
            side_effect=capturing_ntf,
        ), patch("builtins.open", side_effect=tracking_open):
            result = runner.run(large_prompt, output_file, log_file)

        assert result is True

        args, kwargs = mock_popen.call_args
        cmd = args[0]

        # The large prompt should NOT appear in the command list
        assert large_prompt not in cmd, (
            "Large prompts must not be passed as CLI arguments"
        )
        # stdin should be set (to the opened temp file handle)
        assert "stdin" in kwargs, (
            "Large prompts must use stdin= to pass content"
        )
        # stdin should not be PIPE — it should be a file handle
        stdin_handle = kwargs["stdin"]
        assert stdin_handle != subprocess.PIPE, (
            "Large prompts should use a file handle, not subprocess.PIPE"
        )
        # The stdin handle must point to the same temp file that received the prompt
        assert len(captured_tmpfile_name) == 1, "Expected exactly one temp file"
        assert stdin_handle.name == captured_tmpfile_name[0], (
            "stdin handle must be opened from the temp file that received the prompt"
        )
        # Verify the stdin handle is a reopened file (via open()), not the writer
        assert len(captured_open_calls) >= 1, (
            "Expected open() to be called on the temp file path (reopen step)"
        )
        assert stdin_handle is captured_open_calls[0], (
            "stdin must be the handle returned by open(tmpfile.name), not the writer"
        )
        # The temp file must contain the large prompt
        written = "".join(captured_content)
        assert large_prompt in written, (
            "The stdin temp file must contain the large prompt"
        )

    def test_small_prompt_uses_devnull_stdin(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        small_prompt = "short prompt"

        mock_proc = _make_mock_proc([b"response", b""], returncode=0)

        with patch(
            "orchestrator_v3.research.subprocess.Popen", return_value=mock_proc
        ) as mock_popen:
            runner.run(small_prompt, output_file, log_file)

        args, kwargs = mock_popen.call_args
        cmd = args[0]
        assert cmd[-1] == small_prompt
        assert kwargs.get("stdin") == subprocess.DEVNULL


# ── 3.9  _run_parallel both succeed ──────────────────────────────────


class TestRunParallelBothSucceed:
    """3.9: _run_parallel returns (True, True) when both runners succeed."""

    def test_both_succeed(self, tmp_path):
        settings = OrchestratorSettings(repo_root=tmp_path)
        settings.research_dir.mkdir(parents=True, exist_ok=True)
        slug = "test_parallel_ok"
        research_dir = settings.research_dir / slug
        research_dir.mkdir(parents=True)
        (research_dir / "logs").mkdir(parents=True)

        sm = ResearchStateManager(state_path=research_dir / "state.json")
        sm.init(slug=slug, question="Test?")
        pb = ResearchPromptBuilder(question="Test?", intent="", slug=slug)

        # Use mock runners that write output files and return True
        claude = MagicMock(spec=ClaudeRunner)
        claude.timeout = 1800
        claude.proc = None

        def claude_run(prompt, output_file, log_file):
            output_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("Opus analysis content")
            log_file.write_text("log")
            return True

        claude.run = claude_run

        codex = MagicMock(spec=CodexReviewer)
        codex.timeout = 600
        codex.proc = None

        def codex_review(prompt, review_file, log_file):
            review_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            # _run_codex reads from log_file and writes stripped output
            log_file.write_text("codex\nCodex review content")
            return True

        codex.run_review = codex_review

        display = MagicMock()

        loop = ResearchLoop(
            state_manager=sm,
            prompt_builder=pb,
            claude_runner=claude,
            codex_runner=codex,
            display=display,
            settings=settings,
            slug=slug,
        )

        opus_ok, codex_ok = loop._run_parallel(
            opus_prompt="opus prompt",
            opus_artifact="opus_initial.md",
            opus_log="opus_initial.log",
            codex_prompt="codex prompt",
            codex_artifact="codex_initial.md",
            codex_log="codex_initial.log",
            phase=1,
        )

        assert opus_ok is True
        assert codex_ok is True

        # Verify the Opus artifact was written by claude.run
        opus_artifact = research_dir / "opus_initial.md"
        assert opus_artifact.exists()
        assert len(opus_artifact.read_text()) > 0

        # Verify the Codex artifact was written by _run_codex
        codex_artifact_path = research_dir / "codex_initial.md"
        assert codex_artifact_path.exists(), "Codex artifact should be written by _run_codex"
        assert len(codex_artifact_path.read_text()) > 0, "Codex artifact should be non-empty"


# ── 3.10  _run_parallel passes explicit timeout to future.result() ──


class TestRunParallelFutureResultTimeout:
    """3.10: future.result() gets timeout=runner.timeout + 60."""

    def test_timeout_argument_matches_runner_plus_60(self, tmp_path):
        settings = OrchestratorSettings(repo_root=tmp_path)
        settings.research_dir.mkdir(parents=True, exist_ok=True)
        slug = "test_timeout_arg"
        research_dir = settings.research_dir / slug
        research_dir.mkdir(parents=True)
        (research_dir / "logs").mkdir(parents=True)

        sm = ResearchStateManager(state_path=research_dir / "state.json")
        sm.init(slug=slug, question="Test?")
        pb = ResearchPromptBuilder(question="Test?", intent="", slug=slug)

        claude_timeout = 1800
        codex_timeout = 600

        claude = ClaudeRunner(model="opus", timeout=claude_timeout, idle_timeout=600)
        codex = CodexReviewer(model="gpt-5.4", timeout=codex_timeout, idle_timeout=600)
        display = MagicMock()

        loop = ResearchLoop(
            state_manager=sm,
            prompt_builder=pb,
            claude_runner=claude,
            codex_runner=codex,
            display=display,
            settings=settings,
            slug=slug,
        )

        # Mock futures that succeed
        mock_opus_future = MagicMock(spec=Future)
        mock_opus_future.result = MagicMock(return_value=True)
        mock_codex_future = MagicMock(spec=Future)
        mock_codex_future.result = MagicMock(return_value=True)

        mock_executor = MagicMock(spec=ThreadPoolExecutor)
        mock_executor.submit = MagicMock(
            side_effect=[mock_opus_future, mock_codex_future]
        )

        with patch("orchestrator_v3.research.ThreadPoolExecutor", return_value=mock_executor):
            loop._run_parallel(
                opus_prompt="p1", opus_artifact="a1.md", opus_log="l1.log",
                codex_prompt="p2", codex_artifact="a2.md", codex_log="l2.log",
                phase=1,
            )

        # Verify the timeout argument passed to each future.result()
        mock_opus_future.result.assert_called_once_with(
            timeout=claude_timeout + 60,
        )
        mock_codex_future.result.assert_called_once_with(
            timeout=codex_timeout + 60,
        )


# ── 3.11  ClaudeRunner strips all Claude session env vars ─────────────


class TestClaudeRunnerEnvStripping:
    """3.11: ClaudeRunner strips CLAUDECODE, CLAUDE_CODE_*, CLAUDE_AGENT_SDK_*."""

    def test_strips_claude_env_vars(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        mock_proc = _make_mock_proc([b"output", b""], returncode=0)

        fake_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/test",
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION": "abc123",
            "CLAUDE_CODE_SOMETHING": "val",
            "CLAUDE_AGENT_SDK_TOKEN": "tok",
            "UNRELATED_VAR": "keep",
        }

        with patch("orchestrator_v3.research.os.environ", fake_env), \
             patch("orchestrator_v3.research.subprocess.Popen", return_value=mock_proc) as mock_popen:
            runner.run("test prompt", output_file, log_file)

        _, kwargs = mock_popen.call_args
        env = kwargs["env"]
        assert "CLAUDECODE" not in env
        assert "CLAUDE_CODE_SESSION" not in env
        assert "CLAUDE_CODE_SOMETHING" not in env
        assert "CLAUDE_AGENT_SDK_TOKEN" not in env
        assert env["UNRELATED_VAR"] == "keep"
        assert env["PATH"] == "/usr/bin"


# ── 3.12  ClaudeRunner uses start_new_session=True ────────────────────


class TestClaudeRunnerStartNewSession:
    """3.12: Both Popen paths use start_new_session=True."""

    def test_small_prompt_start_new_session(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        mock_proc = _make_mock_proc([b"output", b""], returncode=0)

        with patch(
            "orchestrator_v3.research.subprocess.Popen", return_value=mock_proc
        ) as mock_popen:
            runner.run("small prompt", output_file, log_file)

        _, kwargs = mock_popen.call_args
        assert kwargs.get("start_new_session") is True

    def test_large_prompt_start_new_session(self, tmp_path):
        runner = ClaudeRunner(model="opus", timeout=30, idle_timeout=30)
        output_file = tmp_path / "output.md"
        log_file = tmp_path / "output.log"

        large_prompt = "x" * 110_000

        mock_proc = _make_mock_proc([b"response", b""], returncode=0)

        with patch(
            "orchestrator_v3.research.subprocess.Popen", return_value=mock_proc
        ) as mock_popen, patch(
            "orchestrator_v3.research.tempfile.NamedTemporaryFile",
        ) as mock_ntf:
            # Set up the mock temp file
            mock_file = MagicMock()
            mock_file.name = "/tmp/fake_prompt.txt"
            mock_ntf.return_value = mock_file

            import builtins
            original_open = builtins.open
            def fake_open(*a, **kw):
                if len(a) > 0 and str(a[0]) == "/tmp/fake_prompt.txt":
                    return MagicMock()
                return original_open(*a, **kw)

            with patch("builtins.open", side_effect=fake_open):
                runner.run(large_prompt, output_file, log_file)

        _, kwargs = mock_popen.call_args
        assert kwargs.get("start_new_session") is True


# ── 3.13  CodexReviewer uses stdin=DEVNULL and start_new_session ──────


class TestCodexReviewerSubprocessHardening:
    """3.13: CodexReviewer uses stdin=DEVNULL and start_new_session=True."""

    def test_stdin_devnull(self, tmp_path):
        reviewer = CodexReviewer(model="gpt-5.4", timeout=60, idle_timeout=60)
        review_file = tmp_path / "review.md"
        log_file = tmp_path / "review.log"

        mock_proc = _make_mock_proc([b"Review output", b""], returncode=0)

        with patch(
            "orchestrator_v3.reviewer.subprocess.Popen", return_value=mock_proc
        ) as mock_popen:
            reviewer.run_review("test prompt", review_file, log_file)

        _, kwargs = mock_popen.call_args
        assert kwargs.get("stdin") == subprocess.DEVNULL

    def test_start_new_session(self, tmp_path):
        reviewer = CodexReviewer(model="gpt-5.4", timeout=60, idle_timeout=60)
        review_file = tmp_path / "review.md"
        log_file = tmp_path / "review.log"

        mock_proc = _make_mock_proc([b"Review output", b""], returncode=0)

        with patch(
            "orchestrator_v3.reviewer.subprocess.Popen", return_value=mock_proc
        ) as mock_popen:
            reviewer.run_review("test prompt", review_file, log_file)

        _, kwargs = mock_popen.call_args
        assert kwargs.get("start_new_session") is True
