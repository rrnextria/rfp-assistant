"""Integration tests for the deployment flow.

Covers bootstrap gate (__main__._bootstrap), preflight wiring for each
workflow command, env-check bypass for query commands and doctor, and
venv validation/recreate behaviour.

Acceptance gate: at least 14 tests.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from typer.testing import CliRunner

from orchestrator_v3.cli import app
from orchestrator_v3.env_checks import EnvCheckResult

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_how_to(tmp_path: Path) -> Path:
    """Create a minimal how_to/ tree with requirements.txt."""
    how_to = tmp_path / "how_to"
    pkg_dir = how_to / "orchestrator_v3"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "requirements.txt").write_text("pydantic>=2.0\ntyper>=0.9.0\n")
    return how_to


def _make_healthy_venv(how_to: Path) -> Path:
    """Create a fake .venv with a python binary placeholder and matching requirements hash."""
    from orchestrator_v3.bootstrap import _requirements_hash

    venv_dir = how_to / ".venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)
    py = bin_dir / "python"
    py.write_text("#!/fake")
    py.chmod(0o755)
    # Write matching requirements hash so staleness check passes
    (venv_dir / ".requirements_hash").write_text(_requirements_hash(how_to))
    return venv_dir


# ---------------------------------------------------------------------------
# 4.1  --setup-env calls ensure_venv and exits
# ---------------------------------------------------------------------------


class TestSetupEnvFlow:
    def test_setup_env_invokes_ensure_venv(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_py = how_to / ".venv" / "bin" / "python"
        fake_main_file = how_to / "orchestrator_v3" / "__main__.py"
        fake_main_file.write_text("")

        from orchestrator_v3 import __main__ as main_mod

        with patch.object(main_mod, "__file__", str(fake_main_file)), \
             patch.object(main_mod.sys, "argv", ["prog", "--setup-env"]), \
             patch.object(main_mod.sys, "exit", side_effect=SystemExit(0)), \
             patch("orchestrator_v3.bootstrap.ensure_venv", return_value=venv_py) as mock_ensure, \
             patch("orchestrator_v3.cli.app") as mock_app:
            with pytest.raises(SystemExit):
                main_mod._bootstrap()

        mock_ensure.assert_called_once_with(how_to)
        mock_app.assert_not_called()


# ---------------------------------------------------------------------------
# 4.2  --reset-env calls reset_venv and exits
# ---------------------------------------------------------------------------


class TestResetEnvFlow:
    def test_reset_env_invokes_reset_venv(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_py = how_to / ".venv" / "bin" / "python"
        fake_main_file = how_to / "orchestrator_v3" / "__main__.py"
        fake_main_file.write_text("")

        from orchestrator_v3 import __main__ as main_mod

        with patch.object(main_mod, "__file__", str(fake_main_file)), \
             patch.object(main_mod.sys, "argv", ["prog", "--reset-env"]), \
             patch.object(main_mod.sys, "exit", side_effect=SystemExit(0)), \
             patch("orchestrator_v3.bootstrap.reset_venv", return_value=venv_py) as mock_reset:
            with pytest.raises(SystemExit):
                main_mod._bootstrap()

        mock_reset.assert_called_once_with(how_to)


# ---------------------------------------------------------------------------
# 4.3  doctor output includes all expected check names
# ---------------------------------------------------------------------------


class TestDoctorOutput:
    def test_doctor_includes_all_check_names(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Create .git so repo_root check passes
        (tmp_path / ".git").mkdir()
        # Create expected directories
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        # Mock the venv check to avoid real subprocess calls
        with patch("orchestrator_v3.env_checks.check_venv") as mock_venv:
            mock_venv.return_value = EnvCheckResult(
                name="venv", status="PASS", message="healthy", fix_hint=""
            )
            result = runner.invoke(app, ["doctor"])

        output = result.output
        expected_checks = [
            "repo_root",
            "cli:claude",
            "cli:codex",
            "dir:active_plans",
            "dir:reviews",
            "dir:research",
            "python_version",
            "pkg:pydantic",
            "pkg:typer",
            "venv",
        ]
        for check_name in expected_checks:
            assert check_name in output, (
                f"Expected check '{check_name}' not found in doctor output:\n{output}"
            )


# ---------------------------------------------------------------------------
# 4.4  preflight blocks command when required tool is missing
# ---------------------------------------------------------------------------


class TestPreflightBlocksMissingTool:
    def test_plan_blocked_when_codex_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        plan_file = tmp_path / "active_plans" / "test.md"
        plan_file.write_text("# Plan\n")

        original_which = __import__("shutil").which

        def fake_which(name):
            if name == "codex":
                return None
            return original_which(name)

        with patch("orchestrator_v3.env_checks.shutil.which", side_effect=fake_which):
            result = runner.invoke(app, ["plan", str(plan_file)])

        assert result.exit_code == 1
        # Typer CliRunner merges stdout and stderr into result.output
        assert "FAIL" in result.output
        assert "codex" in result.output.lower()


# ---------------------------------------------------------------------------
# 4.5  preflight allows command when --skip-preflight is passed
# ---------------------------------------------------------------------------


class TestPreflightSkip:
    def test_plan_allowed_with_skip_preflight(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        plan_file = tmp_path / "active_plans" / "test.md"
        plan_file.write_text("# Plan\n")

        # Mock both _run_env_preflight and the loop.run to prevent real execution
        with patch("orchestrator_v3.cli._run_env_preflight") as mock_preflight, \
             patch("orchestrator_v3.loop.OrchestratorLoop.run", return_value=0):
            result = runner.invoke(app, ["plan", str(plan_file), "--skip-preflight", "--init"])

        # With --skip-preflight, _run_env_preflight should NOT be called
        mock_preflight.assert_not_called()
        assert "ENVIRONMENT CHECK FAILED" not in result.output


# ---------------------------------------------------------------------------
# 4.6  venv validation/recreate when import probe fails
# ---------------------------------------------------------------------------


class TestVenvValidateRecreate:
    @patch("orchestrator_v3.bootstrap._create_venv")
    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_unhealthy_venv_is_deleted_and_recreated(
        self, mock_run, mock_create, tmp_path, capsys
    ):
        how_to = _make_how_to(tmp_path)
        venv_dir = _make_healthy_venv(how_to)

        # Import probe returns non-zero (unhealthy)
        mock_run.return_value = MagicMock(returncode=1)

        from orchestrator_v3.bootstrap import ensure_venv, _venv_python

        result = ensure_venv(how_to)

        captured = capsys.readouterr()
        assert "unhealthy" in captured.out.lower()

        # _create_venv should have been called to rebuild
        mock_create.assert_called_once_with(how_to / ".venv", how_to)
        assert result == _venv_python(how_to / ".venv")

        # The old venv dir should have been removed before recreation
        # (since _create_venv is mocked, the dir was removed by _remove_venv
        # but not re-created, so it should not exist)
        assert not venv_dir.exists()


# ---------------------------------------------------------------------------
# 4.7  preflight ordering: FAIL before plan-file parsing
# ---------------------------------------------------------------------------


class TestPreflightOrdering:
    def test_fail_message_before_plan_parsing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        # Create a complex plan structure (with phases/ dir) so that
        # verify_plan_syntax would be reachable if preflight didn't block
        plan_dir = tmp_path / "active_plans" / "test_slug"
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)
        plan_file = plan_dir / "test_slug_master_plan.md"
        plan_file.write_text("# Plan\n")
        (phases_dir / "phase_0.md").write_text("# Phase 0\n")

        def fake_which(name):
            if name == "codex":
                return None
            return __import__("shutil").which(name)

        # Patch plan-parsing and verification logic to raise if reached,
        # proving preflight blocks before any plan processing
        with patch("orchestrator_v3.env_checks.shutil.which", side_effect=fake_which), \
             patch("orchestrator_v3.loop.OrchestratorLoop.run",
                   side_effect=AssertionError("plan parsing should not be reached")) as mock_loop, \
             patch("orchestrator_v3.cli.verify_plan_syntax",
                   side_effect=AssertionError("verify_plan_syntax should not be reached")) as mock_verify:
            result = runner.invoke(app, ["plan", str(plan_file), "--init"])

        # Preflight failure should appear
        assert "FAIL" in result.output
        assert "codex" in result.output.lower()
        # The exit code should be 1 from preflight, not from missing file
        assert result.exit_code == 1
        # Neither plan parsing nor verification should have been called
        mock_loop.assert_not_called()
        mock_verify.assert_not_called()


# ---------------------------------------------------------------------------
# 4.8  env check bypass: doctor, --setup-env, --reset-env skip run_env_checks
# ---------------------------------------------------------------------------


class TestEnvCheckBypass:
    def test_doctor_does_not_call_run_env_checks(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        with patch("orchestrator_v3.env_checks.run_env_checks") as mock_run, \
             patch("orchestrator_v3.env_checks.check_venv") as mock_venv:
            mock_venv.return_value = EnvCheckResult(
                name="venv", status="PASS", message="ok", fix_hint=""
            )
            runner.invoke(app, ["doctor"])

        mock_run.assert_not_called()

    def test_setup_env_does_not_call_run_env_checks(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_py = how_to / ".venv" / "bin" / "python"
        fake_main_file = how_to / "orchestrator_v3" / "__main__.py"
        fake_main_file.write_text("")

        from orchestrator_v3 import __main__ as main_mod

        with patch.object(main_mod, "__file__", str(fake_main_file)), \
             patch.object(main_mod.sys, "argv", ["prog", "--setup-env"]), \
             patch.object(main_mod.sys, "exit", side_effect=SystemExit(0)), \
             patch("orchestrator_v3.bootstrap.ensure_venv", return_value=venv_py), \
             patch("orchestrator_v3.env_checks.run_env_checks") as mock_run:
            with pytest.raises(SystemExit):
                main_mod._bootstrap()

        mock_run.assert_not_called()

    def test_reset_env_does_not_call_run_env_checks(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_py = how_to / ".venv" / "bin" / "python"
        fake_main_file = how_to / "orchestrator_v3" / "__main__.py"
        fake_main_file.write_text("")

        from orchestrator_v3 import __main__ as main_mod

        with patch.object(main_mod, "__file__", str(fake_main_file)), \
             patch.object(main_mod.sys, "argv", ["prog", "--reset-env"]), \
             patch.object(main_mod.sys, "exit", side_effect=SystemExit(0)), \
             patch("orchestrator_v3.bootstrap.reset_venv", return_value=venv_py), \
             patch("orchestrator_v3.env_checks.run_env_checks") as mock_run:
            with pytest.raises(SystemExit):
                main_mod._bootstrap()

        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# 4.9  default bootstrap re-exec: outside venv -> os.execve
# ---------------------------------------------------------------------------


class TestBootstrapReExec:
    def test_execve_called_with_venv_python(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_py = how_to / ".venv" / "bin" / "python"
        fake_main_file = how_to / "orchestrator_v3" / "__main__.py"
        fake_main_file.write_text("")

        from orchestrator_v3 import __main__ as main_mod

        with patch.object(main_mod, "__file__", str(fake_main_file)), \
             patch.object(main_mod.sys, "argv", ["prog", "plan", "foo.md"]), \
             patch.object(main_mod.sys, "prefix", "/usr"), \
             patch("orchestrator_v3.bootstrap.ensure_venv", return_value=venv_py) as mock_ensure, \
             patch.object(main_mod.os, "execve") as mock_execve, \
             patch.object(main_mod.os, "environ", {"PATH": "/usr/bin"}), \
             patch.object(main_mod.os, "sep", os.sep):
            main_mod._bootstrap()

        mock_ensure.assert_called_once_with(how_to)
        mock_execve.assert_called_once()

        call_args = mock_execve.call_args
        # First arg: venv python path
        assert call_args[0][0] == str(venv_py)
        # Second arg: argv list preserving original args
        argv = call_args[0][1]
        assert argv[0] == str(venv_py)
        assert "-m" in argv
        assert "orchestrator_v3" in argv
        assert "plan" in argv
        assert "foo.md" in argv
        # Third arg: env dict with PYTHONPATH
        env = call_args[0][2]
        assert "PYTHONPATH" in env
        assert str(how_to) in env["PYTHONPATH"]


# ---------------------------------------------------------------------------
# 4.10  in-venv fallthrough: sys.prefix inside .venv -> app() called
# ---------------------------------------------------------------------------


class TestInVenvFallthrough:
    def test_no_execve_when_already_in_venv(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_dir = _make_healthy_venv(how_to)
        fake_main_file = how_to / "orchestrator_v3" / "__main__.py"
        fake_main_file.write_text("")

        from orchestrator_v3 import __main__ as main_mod

        with patch.object(main_mod, "__file__", str(fake_main_file)), \
             patch.object(main_mod.sys, "argv", ["prog", "doctor"]), \
             patch.object(main_mod.sys, "prefix", str(venv_dir)), \
             patch.object(main_mod.os, "execve") as mock_execve, \
             patch("orchestrator_v3.cli.app") as mock_app:
            main_mod._bootstrap()

        mock_execve.assert_not_called()
        mock_app.assert_called_once()


# ---------------------------------------------------------------------------
# 4.11  research preflight wiring
# ---------------------------------------------------------------------------


class TestResearchPreflightWiring:
    def test_research_fails_when_claude_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        original_which = __import__("shutil").which

        def fake_which(name):
            if name == "claude":
                return None
            return original_which(name)

        with patch("orchestrator_v3.env_checks.shutil.which", side_effect=fake_which):
            result = runner.invoke(app, ["research", "What is X?"])

        assert "FAIL" in result.output
        assert "claude" in result.output.lower()
        assert result.exit_code == 1

    def test_research_skip_preflight_bypasses(self, tmp_path, monkeypatch):
        """--skip-preflight prevents _run_env_preflight from being called."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        with patch("orchestrator_v3.cli._run_env_preflight") as mock_preflight, \
             patch("orchestrator_v3.research.ResearchLoop.run", return_value=0):
            result = runner.invoke(
                app, ["research", "What is X?", "--skip-preflight"]
            )

        mock_preflight.assert_not_called()
        assert "ENVIRONMENT CHECK FAILED" not in result.output


# ---------------------------------------------------------------------------
# 4.12  postmortem preflight wiring
# ---------------------------------------------------------------------------


class TestPostmortemPreflightWiring:
    def test_postmortem_fails_when_codex_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        original_which = __import__("shutil").which

        def fake_which(name):
            if name == "codex":
                return None
            return original_which(name)

        with patch("orchestrator_v3.env_checks.shutil.which", side_effect=fake_which):
            result = runner.invoke(app, ["postmortem", "some_slug"])

        assert "FAIL" in result.output
        assert "codex" in result.output.lower()
        assert result.exit_code == 1

    def test_postmortem_skip_preflight_bypasses(self, tmp_path, monkeypatch):
        """--skip-preflight prevents _run_env_preflight from being called."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        with patch("orchestrator_v3.cli._run_env_preflight") as mock_preflight:
            # postmortem with --skip-preflight will find no artifacts and exit 0
            result = runner.invoke(
                app, ["postmortem", "some_slug", "--skip-preflight",
                      "--skip-reflection"]
            )

        mock_preflight.assert_not_called()
        assert "ENVIRONMENT CHECK FAILED" not in result.output


# ---------------------------------------------------------------------------
# 4.13  code preflight wiring
# ---------------------------------------------------------------------------


class TestCodePreflightWiring:
    def test_code_fails_when_codex_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        original_which = __import__("shutil").which

        def fake_which(name):
            if name == "codex":
                return None
            return original_which(name)

        with patch("orchestrator_v3.env_checks.shutil.which", side_effect=fake_which):
            result = runner.invoke(app, ["code", "myslug", "0", "1"])

        assert "FAIL" in result.output
        assert "codex" in result.output.lower()
        assert result.exit_code == 1

    def test_code_skip_preflight_bypasses(self, tmp_path, monkeypatch):
        """--skip-preflight prevents _run_env_preflight from being called."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        for d in ("active_plans", "reviews", "research"):
            (tmp_path / d).mkdir()

        # Create a plan file so the code command does not error before the
        # preflight check assertion is exercised
        plan_dir = tmp_path / "active_plans" / "myslug"
        plan_dir.mkdir(parents=True)
        (plan_dir / "myslug_master_plan.md").write_text("# Plan\n")

        with patch("orchestrator_v3.cli._run_env_preflight") as mock_preflight, \
             patch("orchestrator_v3.loop.OrchestratorLoop.run", return_value=0):
            result = runner.invoke(
                app, ["code", "myslug", "0", "1", "--skip-preflight", "--init"]
            )

        mock_preflight.assert_not_called()
        assert "ENVIRONMENT CHECK FAILED" not in result.output


# ---------------------------------------------------------------------------
# 4.14  query-command preflight exemption
# ---------------------------------------------------------------------------


class TestQueryCommandPreflightExemption:
    def test_status_does_not_run_env_checks(self, tmp_path, monkeypatch):
        """status is a query command and must NOT invoke run_env_checks,
        even when all CLI tools are missing and there is no git repo."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reviews").mkdir()

        # Hostile environment: all tools missing, no git repo
        with patch("orchestrator_v3.env_checks.shutil.which", return_value=None), \
             patch("orchestrator_v3.config.subprocess.run",
                   side_effect=FileNotFoundError("git not installed")), \
             patch("orchestrator_v3.cli._run_env_preflight") as mock_preflight, \
             patch("orchestrator_v3.env_checks.run_env_checks") as mock_run:
            result = runner.invoke(app, ["status", "nonexistent"])

        mock_preflight.assert_not_called()
        mock_run.assert_not_called()
        assert "ENVIRONMENT CHECK FAILED" not in result.output
        assert "preflight" not in result.output.lower()

    def test_plan_verify_does_not_run_env_checks(self, tmp_path, monkeypatch):
        """plan-verify is a query command and must NOT invoke run_env_checks,
        even when all CLI tools are missing and there is no git repo."""
        monkeypatch.chdir(tmp_path)
        plan_file = tmp_path / "test_plan.md"
        plan_file.write_text("# Simple Plan\n\n## Tasks\n### [ ] 1 Do something\n")

        # Hostile environment: all tools missing, no git repo
        with patch("orchestrator_v3.env_checks.shutil.which", return_value=None), \
             patch("orchestrator_v3.config.subprocess.run",
                   side_effect=FileNotFoundError("git not installed")), \
             patch("orchestrator_v3.cli._run_env_preflight") as mock_preflight, \
             patch("orchestrator_v3.env_checks.run_env_checks") as mock_run:
            result = runner.invoke(app, ["plan-verify", str(plan_file)])

        mock_preflight.assert_not_called()
        mock_run.assert_not_called()
        assert "ENVIRONMENT CHECK FAILED" not in result.output
        # plan-verify may output "FAIL" for plan syntax issues, which is
        # expected and not a preflight failure
        assert "preflight" not in result.output.lower()
