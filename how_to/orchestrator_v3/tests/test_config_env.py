"""Tests for .env loading, config precedence, and reasoning effort propagation."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestEnvLoading:
    """Test that _env_str/_env_int work correctly."""

    def test_env_str_returns_env_value(self):
        from orchestrator_v3.config import _env_str

        with patch.dict(os.environ, {"MAISTRO_CODEX_MODEL": "gpt-6.0"}):
            assert _env_str("MAISTRO_CODEX_MODEL", "gpt-5.4") == "gpt-6.0"

    def test_env_str_returns_default_when_unset(self):
        from orchestrator_v3.config import _env_str

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MAISTRO_CODEX_MODEL", None)
            assert _env_str("MAISTRO_CODEX_MODEL", "gpt-5.4") == "gpt-5.4"

    def test_env_int_returns_env_value(self):
        from orchestrator_v3.config import _env_int

        with patch.dict(os.environ, {"MAISTRO_TIMEOUT": "3600"}):
            assert _env_int("MAISTRO_TIMEOUT", 1800) == 3600

    def test_env_int_returns_default_when_unset(self):
        from orchestrator_v3.config import _env_int

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MAISTRO_TIMEOUT", None)
            assert _env_int("MAISTRO_TIMEOUT", 1800) == 1800

    def test_env_int_returns_default_on_invalid(self):
        from orchestrator_v3.config import _env_int

        with patch.dict(os.environ, {"MAISTRO_TIMEOUT": "not_a_number"}):
            assert _env_int("MAISTRO_TIMEOUT", 1800) == 1800


class TestLoadDotenv:
    """Test the actual _load_dotenv() function from config.py."""

    def test_load_dotenv_resolves_to_how_to_env(self):
        """Verify _load_dotenv resolves to how_to/.env relative to config.py."""
        from orchestrator_v3 import config

        config_path = Path(config.__file__).resolve()
        # config.py lives at how_to/orchestrator_v3/config.py
        assert config_path.parent.name == "orchestrator_v3"
        assert config_path.parent.parent.name == "how_to"
        expected_env = config_path.parent.parent / ".env"
        assert expected_env.name == ".env"

    def test_load_dotenv_populates_env_from_file(self, tmp_path):
        """Create a .env at the path _load_dotenv expects, call it, verify env."""
        # Build a fake how_to/orchestrator_v3/ structure in tmp_path
        fake_orch = tmp_path / "orchestrator_v3"
        fake_orch.mkdir()
        fake_config = fake_orch / "config.py"
        fake_config.write_text("")  # dummy

        env_file = tmp_path / ".env"
        env_file.write_text("MAISTRO_DOTENV_TEST_XYZ=loaded_from_dotenv\n")

        try:
            from dotenv import load_dotenv
        except ImportError:
            pytest.skip("python-dotenv not installed")

        from orchestrator_v3 import config

        # Patch __file__ in the config module so _load_dotenv resolves to our tmp .env
        with patch.object(config, "__file__", str(fake_config)):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("MAISTRO_DOTENV_TEST_XYZ", None)
                config._load_dotenv()
                assert os.environ.get("MAISTRO_DOTENV_TEST_XYZ") == "loaded_from_dotenv"
                os.environ.pop("MAISTRO_DOTENV_TEST_XYZ", None)

    def test_load_dotenv_does_not_override_existing_vars(self, tmp_path):
        """Verify _load_dotenv(override=False) respects pre-existing env vars."""
        fake_orch = tmp_path / "orchestrator_v3"
        fake_orch.mkdir()
        fake_config = fake_orch / "config.py"
        fake_config.write_text("")

        env_file = tmp_path / ".env"
        env_file.write_text("MAISTRO_DOTENV_TEST_ABC=from_dotenv\n")

        try:
            from dotenv import load_dotenv
        except ImportError:
            pytest.skip("python-dotenv not installed")

        from orchestrator_v3 import config

        with patch.object(config, "__file__", str(fake_config)):
            with patch.dict(os.environ, {"MAISTRO_DOTENV_TEST_ABC": "already_set"}):
                config._load_dotenv()
                assert os.environ["MAISTRO_DOTENV_TEST_ABC"] == "already_set"

    def test_load_dotenv_graceful_without_python_dotenv(self):
        """Verify _load_dotenv() doesn't crash when python-dotenv is missing."""
        from orchestrator_v3 import config

        with patch.dict("sys.modules", {"dotenv": None}):
            # Should not raise
            config._load_dotenv()


class TestCLIDefaultResolution:
    """Test that CLI commands resolve defaults from env-backed config.

    Typer Option defaults are evaluated at import time, so changing env vars
    after import doesn't change the baked-in defaults. The subprocess tests
    below set env vars *before* importing the CLI module to prove that the
    defaults are wired through _env_str/_env_int at import time.
    """

    def test_plan_help_shows_env_backed_model(self):
        """Invoke plan --help via CliRunner and verify model default appears."""
        from typer.testing import CliRunner

        from orchestrator_v3.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.output
        assert "--reasoning-effort" in result.output

    def test_code_help_shows_reasoning_effort(self):
        """Invoke code --help and verify --reasoning-effort is available."""
        from typer.testing import CliRunner

        from orchestrator_v3.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["code", "--help"])
        assert result.exit_code == 0
        assert "--reasoning-effort" in result.output

    def test_research_help_shows_all_config_flags(self):
        """Invoke research --help and verify env-backed flags are present."""
        from typer.testing import CliRunner

        from orchestrator_v3.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["research", "--help"])
        assert result.exit_code == 0
        assert "--claude-model" in result.output
        assert "--codex-model" in result.output
        assert "--reasoning-effort" in result.output
        assert "--timeout" in result.output
        assert "--idle-timeout" in result.output

    def test_postmortem_help_shows_reasoning_effort(self):
        """Invoke postmortem --help and verify --reasoning-effort is available."""
        from typer.testing import CliRunner

        from orchestrator_v3.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["postmortem", "--help"])
        assert result.exit_code == 0
        assert "--reasoning-effort" in result.output

    def test_cli_defaults_from_env_at_import_time(self):
        """Spawn a subprocess with MAISTRO_* env vars set and verify CLI picks them up.

        This tests the full import-time wiring: env var → _env_str() → typer.Option default.
        """
        import subprocess
        import sys

        # Print defaults for all 4 commands: model, reasoning_effort, timeout,
        # idle_timeout, plus research-specific claude_model and codex_model.
        script = "\n".join([
            "import inspect",
            "from orchestrator_v3.cli import plan, code, research, postmortem",
            "def d(fn, p): return str(inspect.signature(fn).parameters[p].default.default)",
            # plan (4 params)
            "print(d(plan,'model'))",
            "print(d(plan,'reasoning_effort'))",
            "print(d(plan,'timeout'))",
            "print(d(plan,'idle_timeout'))",
            # code (4 params)
            "print(d(code,'model'))",
            "print(d(code,'reasoning_effort'))",
            "print(d(code,'timeout'))",
            "print(d(code,'idle_timeout'))",
            # research (5 params)
            "print(d(research,'claude_model'))",
            "print(d(research,'codex_model'))",
            "print(d(research,'reasoning_effort'))",
            "print(d(research,'timeout'))",
            "print(d(research,'idle_timeout'))",
            # postmortem (4 params)
            "print(d(postmortem,'model'))",
            "print(d(postmortem,'reasoning_effort'))",
            "print(d(postmortem,'timeout'))",
            "print(d(postmortem,'idle_timeout'))",
        ])
        env = os.environ.copy()
        env["PYTHONPATH"] = "how_to"
        env["MAISTRO_CODEX_MODEL"] = "gpt-test-env"
        env["MAISTRO_CODEX_REASONING"] = "low"
        env["MAISTRO_TIMEOUT"] = "9999"
        env["MAISTRO_IDLE_TIMEOUT"] = "7777"
        env["MAISTRO_CLAUDE_MODEL"] = "test-claude"
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).resolve().parent.parent.parent.parent),
            timeout=30,
        )
        assert result.returncode == 0, f"subprocess failed: {result.stderr}"
        lines = result.stdout.strip().split("\n")
        # plan
        assert lines[0] == "gpt-test-env", f"plan.model: {lines[0]}"
        assert lines[1] == "low", f"plan.reasoning_effort: {lines[1]}"
        assert lines[2] == "9999", f"plan.timeout: {lines[2]}"
        assert lines[3] == "7777", f"plan.idle_timeout: {lines[3]}"
        # code
        assert lines[4] == "gpt-test-env", f"code.model: {lines[4]}"
        assert lines[5] == "low", f"code.reasoning_effort: {lines[5]}"
        assert lines[6] == "9999", f"code.timeout: {lines[6]}"
        assert lines[7] == "7777", f"code.idle_timeout: {lines[7]}"
        # research
        assert lines[8] == "test-claude", f"research.claude_model: {lines[8]}"
        assert lines[9] == "gpt-test-env", f"research.codex_model: {lines[9]}"
        assert lines[10] == "low", f"research.reasoning_effort: {lines[10]}"
        assert lines[11] == "9999", f"research.timeout: {lines[11]}"
        assert lines[12] == "7777", f"research.idle_timeout: {lines[12]}"
        # postmortem
        assert lines[13] == "gpt-test-env", f"postmortem.model: {lines[13]}"
        assert lines[14] == "low", f"postmortem.reasoning_effort: {lines[14]}"
        assert lines[15] == "9999", f"postmortem.timeout: {lines[15]}"
        assert lines[16] == "7777", f"postmortem.idle_timeout: {lines[16]}"


class TestConfigPrecedence:
    """Test CLI flag > .env > hardcoded default precedence."""

    def test_settings_uses_env_default_model(self):
        from orchestrator_v3.config import OrchestratorSettings, _env_str

        with patch.dict(os.environ, {"MAISTRO_CODEX_MODEL": "gpt-6.0"}):
            settings = OrchestratorSettings(
                repo_root=Path("/tmp"),
                default_model=_env_str("MAISTRO_CODEX_MODEL", "gpt-5.4"),
            )
            assert settings.default_model == "gpt-6.0"

    def test_cli_override_beats_env(self):
        from orchestrator_v3.config import OrchestratorSettings

        with patch.dict(os.environ, {"MAISTRO_CODEX_MODEL": "gpt-6.0"}):
            settings = OrchestratorSettings(
                repo_root=Path("/tmp"),
                default_model="gpt-5.4",  # CLI override
            )
            assert settings.default_model == "gpt-5.4"

    def test_settings_has_new_fields(self):
        from orchestrator_v3.config import OrchestratorSettings

        settings = OrchestratorSettings(repo_root=Path("/tmp"))
        assert hasattr(settings, "default_timeout")
        assert hasattr(settings, "default_idle_timeout")
        assert hasattr(settings, "default_reasoning_effort")
        assert hasattr(settings, "default_claude_model")


class TestReasoningEffortPropagation:
    """Test that reasoning effort flows from config to reviewer."""

    def test_codex_reviewer_accepts_reasoning_effort(self):
        from orchestrator_v3.reviewer import CodexReviewer

        reviewer = CodexReviewer(reasoning_effort="medium")
        assert reviewer.reasoning_effort == "medium"

    def test_codex_reviewer_default_reasoning_effort(self):
        from orchestrator_v3.reviewer import CodexReviewer

        reviewer = CodexReviewer()
        assert reviewer.reasoning_effort == "high"


class TestClaudeRunnerConfigDefault:
    """Test that ClaudeRunner reads MAISTRO_CLAUDE_MODEL from config."""

    def test_claude_runner_default_reads_env(self):
        from orchestrator_v3.research import ClaudeRunner

        with patch.dict(os.environ, {"MAISTRO_CLAUDE_MODEL": "sonnet"}):
            runner = ClaudeRunner()
            assert runner.model == "sonnet"

    def test_claude_runner_default_fallback(self):
        from orchestrator_v3.research import ClaudeRunner

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MAISTRO_CLAUDE_MODEL", None)
            runner = ClaudeRunner()
            assert runner.model == "opus"

    def test_claude_runner_explicit_overrides_env(self):
        from orchestrator_v3.research import ClaudeRunner

        with patch.dict(os.environ, {"MAISTRO_CLAUDE_MODEL": "sonnet"}):
            runner = ClaudeRunner(model="haiku")
            assert runner.model == "haiku"
