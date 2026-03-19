"""Tests for the env_checks module and related CLI/config code.

Phase 2: Environment checks — validates check_python_version,
check_required_packages, check_cli_tools, check_directories,
check_repo_root, run_env_checks, doctor command, --skip-preflight,
and config.detect_repo_root.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from orchestrator_v3.env_checks import (
    EnvCheckResult,
    _COMMAND_TOOLS,
    _find_repo_root,
    check_cli_tools,
    check_directories,
    check_python_version,
    check_repo_root,
    check_required_packages,
    check_venv,
    run_env_checks,
)

runner = CliRunner()


# ── 2.1 check_python_version ────────────────────────────────────────


class TestCheckPythonVersion:
    @staticmethod
    def _fake_version_info(major, minor, micro):
        """Build a mock that behaves like sys.version_info (named-tuple-like)."""
        vi = MagicMock()
        vi.major = major
        vi.minor = minor
        vi.micro = micro
        vi.__ge__ = lambda self, other: (major, minor, micro) >= other[:3]
        vi.__lt__ = lambda self, other: (major, minor, micro) < other[:3]
        return vi

    def test_pass_for_310_plus(self):
        """2.1: check_python_version returns PASS for Python 3.10+."""
        with patch.object(
            sys, "version_info", self._fake_version_info(3, 12, 4)
        ):
            result = check_python_version()
        assert result.status == "PASS"
        assert "3.12.4" in result.message

    def test_warn_for_older(self):
        """2.1: check_python_version returns WARN for Python < 3.10."""
        with patch.object(
            sys, "version_info", self._fake_version_info(3, 9, 1)
        ):
            result = check_python_version()
        assert result.status == "WARN"
        assert "3.10+ recommended" in result.message
        assert result.fix_hint


# ── 2.2 / 2.3 check_required_packages ───────────────────────────────


class TestCheckRequiredPackages:
    def test_pass_when_both_importable(self):
        """2.2: PASS when pydantic and typer are importable."""
        results = check_required_packages()
        # We're running inside a venv that has both packages
        names = {r.name for r in results}
        assert "pkg:pydantic" in names
        assert "pkg:typer" in names
        assert all(r.status == "PASS" for r in results)

    def test_fail_with_install_hint_when_missing(self):
        """2.3: FAIL with install hint when a package is missing."""
        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pydantic":
                raise ImportError("no module pydantic")
            # For the actual importlib.import_module call, delegate normally
            return original_import(name, *args, **kwargs)

        with patch("importlib.import_module", side_effect=fake_import):
            results = check_required_packages()

        pydantic_results = [r for r in results if r.name == "pkg:pydantic"]
        assert len(pydantic_results) == 1
        assert pydantic_results[0].status == "FAIL"
        assert "pip install pydantic" in pydantic_results[0].fix_hint


# ── 2.4 / 2.5 check_cli_tools ───────────────────────────────────────


class TestCheckCliTools:
    def test_pass_when_tool_in_path(self):
        """2.4: check_cli_tools returns PASS when claude is on PATH."""
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            results = check_cli_tools(["claude"])
        assert len(results) == 1
        assert results[0].status == "PASS"
        assert results[0].name == "cli:claude"
        assert "/usr/local/bin/claude" in results[0].message

    def test_fail_with_install_hint_when_not_in_path(self):
        """2.5: check_cli_tools returns FAIL with install hint when not in PATH."""
        with patch("shutil.which", return_value=None):
            results = check_cli_tools(["claude"])
        assert len(results) == 1
        assert results[0].status == "FAIL"
        assert results[0].name == "cli:claude"
        assert "not found" in results[0].message
        assert "npm install" in results[0].fix_hint


# ── 2.6 check_directories ───────────────────────────────────────────


class TestCheckDirectories:
    def test_warn_for_missing_directories(self, tmp_path):
        """2.6: check_directories returns WARN for missing dirs with mkdir hint."""
        results = check_directories(tmp_path)
        # All four directories (active_plans, reviews, research, maistro) should be WARN
        warn_results = [r for r in results if r.status == "WARN"]
        assert len(warn_results) == 4
        for r in warn_results:
            assert "mkdir" in r.fix_hint

    def test_pass_for_existing_directories(self, tmp_path):
        """check_directories returns PASS for existing dirs."""
        for dirname in ("active_plans", "reviews", "research", "maistro"):
            (tmp_path / dirname).mkdir()
        results = check_directories(tmp_path)
        assert all(r.status == "PASS" for r in results)


# ── 2.7 / 2.8 check_repo_root ───────────────────────────────────────


class TestCheckRepoRoot:
    def test_pass_inside_git_repo(self):
        """2.7: check_repo_root returns PASS inside a git repo."""
        with patch(
            "orchestrator_v3.env_checks._find_repo_root",
            return_value=Path("/fake/repo"),
        ):
            result = check_repo_root()
        assert result.status == "PASS"
        assert result.name == "repo_root"

    def test_fail_outside_git_repo(self):
        """2.8: check_repo_root returns FAIL outside a git repo."""
        with patch(
            "orchestrator_v3.env_checks._find_repo_root",
            return_value=None,
        ):
            result = check_repo_root()
        assert result.status == "FAIL"
        assert "not inside" in result.message.lower()
        assert "git init" in result.fix_hint


# ── 2.9 / 2.10 run_env_checks tool mapping ──────────────────────────


class TestRunEnvChecksToolMapping:
    def test_plan_only_checks_codex(self):
        """2.9: run_env_checks('plan') only checks for codex, not claude."""
        with patch(
            "orchestrator_v3.env_checks._find_repo_root",
            return_value=Path("/fake/repo"),
        ), patch(
            "orchestrator_v3.env_checks.check_cli_tools",
            wraps=check_cli_tools,
        ) as mock_cli:
            with patch("shutil.which", return_value="/usr/bin/codex"):
                run_env_checks("plan")
            mock_cli.assert_called_once_with(["codex"])

    def test_research_checks_claude_and_codex(self):
        """2.10: run_env_checks('research') checks for both claude and codex."""
        with patch(
            "orchestrator_v3.env_checks._find_repo_root",
            return_value=Path("/fake/repo"),
        ), patch(
            "orchestrator_v3.env_checks.check_cli_tools",
            wraps=check_cli_tools,
        ) as mock_cli:
            with patch("shutil.which", return_value="/usr/bin/fake"):
                run_env_checks("research")
            mock_cli.assert_called_once_with(["claude", "codex"])


# ── 2.11 doctor output formatting ───────────────────────────────────


class TestDoctorOutput:
    def test_doctor_output_includes_table(self):
        """2.11: doctor output formatting includes all check results in a table."""
        from orchestrator_v3.cli import app

        repo_check = EnvCheckResult(name="repo_root", status="PASS", message="ok")
        cli_claude = EnvCheckResult(name="cli:claude", status="PASS", message="found")
        cli_codex = EnvCheckResult(name="cli:codex", status="WARN", message="missing")
        dir_plans = EnvCheckResult(name="dir:active_plans", status="PASS", message="exists")
        py_ver = EnvCheckResult(name="python_version", status="PASS", message="3.12")
        pkg_check = EnvCheckResult(name="pkg:pydantic", status="PASS", message="ok")
        venv_check = EnvCheckResult(name="venv", status="PASS", message="healthy")

        with patch(
            "orchestrator_v3.env_checks.check_repo_root",
            return_value=repo_check,
        ), patch(
            "orchestrator_v3.env_checks.check_cli_tools",
            return_value=[cli_claude, cli_codex],
        ), patch(
            "orchestrator_v3.env_checks._find_repo_root",
            return_value=Path("/fake"),
        ), patch(
            "orchestrator_v3.env_checks.check_directories",
            return_value=[dir_plans],
        ), patch(
            "orchestrator_v3.env_checks.check_python_version",
            return_value=py_ver,
        ), patch(
            "orchestrator_v3.env_checks.check_required_packages",
            return_value=[pkg_check],
        ), patch(
            "orchestrator_v3.env_checks.check_venv",
            return_value=venv_check,
        ):
            result = runner.invoke(app, ["doctor"])

        output = result.output
        # All named check results should appear in the table
        for name in ("repo_root", "cli:claude", "cli:codex", "dir:active_plans",
                     "python_version", "pkg:pydantic", "venv"):
            assert name in output, f"Check '{name}' not found in doctor output"
        # Status values should appear
        assert "PASS" in output
        assert "WARN" in output
        # Summary should reflect actual counts (6 PASS, 1 WARN, 0 FAIL)
        assert "6 passed" in output
        assert "1 warnings" in output
        assert "0 failures" in output


# ── 2.12 --skip-preflight ───────────────────────────────────────────


class TestSkipPreflight:
    def test_skip_preflight_bypasses_checks(self):
        """2.12: --skip-preflight bypasses all environment checks."""
        from orchestrator_v3.cli import _run_env_preflight

        with patch(
            "orchestrator_v3.env_checks.run_env_checks"
        ) as mock_checks:
            # Without --skip-preflight, _run_env_preflight calls run_env_checks
            mock_checks.return_value = []
            _run_env_preflight("plan")
            mock_checks.assert_called_once()

        # Verify that the plan command with --skip-preflight does NOT call
        # _run_env_preflight (it skips it entirely based on the flag)
        from orchestrator_v3.cli import app

        with patch(
            "orchestrator_v3.cli._run_env_preflight"
        ) as mock_preflight:
            # Invoke plan with --skip-preflight (will fail for other reasons
            # but that's fine -- we just need to verify preflight is skipped)
            result = runner.invoke(
                app,
                [
                    "plan",
                    "nonexistent_plan.md",
                    "--skip-preflight",
                    "--dry-run",
                ],
            )
            mock_preflight.assert_not_called()


# ── 2.13 / 2.14 config.detect_repo_root ─────────────────────────────


class TestDetectRepoRoot:
    def test_returns_repo_root_when_git_succeeds(self, tmp_path):
        """2.13: detect_repo_root returns repo root when git rev-parse succeeds.

        Strategy 1 uses ``Path(__file__)`` which always resolves to the real
        config.py location (inside the real repo).  That means strategy 1
        succeeds in our test environment, so we verify the function returns
        a valid Path that is indeed a git repo root (has ``.git``).
        """
        from orchestrator_v3.config import detect_repo_root

        result = detect_repo_root()
        assert isinstance(result, Path)
        assert (result / ".git").exists()

    def test_returns_repo_root_via_subprocess_fallback(self, tmp_path):
        """2.13b: When strategy 1 fails, subprocess git rev-parse provides root."""
        from orchestrator_v3.config import detect_repo_root

        mock_result = MagicMock()
        mock_result.stdout = str(tmp_path) + "\n"

        # Make the candidate from strategy 1 not have .git
        fake_config = tmp_path / "how_to" / "orchestrator_v3" / "config.py"
        fake_config.parent.mkdir(parents=True, exist_ok=True)
        fake_config.touch()

        import orchestrator_v3.config as config_mod

        original_file = config_mod.__file__
        try:
            config_mod.__file__ = str(fake_config)
            with patch(
                "orchestrator_v3.config.subprocess.run",
                return_value=mock_result,
            ):
                result = detect_repo_root()
        finally:
            config_mod.__file__ = original_file

        assert result == tmp_path

    def test_fallback_to_cwd_on_file_not_found(self, tmp_path, monkeypatch):
        """2.14: Falls back to Path.cwd() when git raises FileNotFoundError."""
        from orchestrator_v3.config import detect_repo_root

        monkeypatch.chdir(tmp_path)

        with patch(
            "orchestrator_v3.config.subprocess.run",
            side_effect=FileNotFoundError("git not installed"),
        ), patch.object(
            Path,
            "exists",
            return_value=False,
        ):
            result = detect_repo_root()
        assert result == Path.cwd()

    def test_fallback_to_cwd_on_called_process_error(self, tmp_path, monkeypatch):
        """2.14: Falls back to Path.cwd() when git raises CalledProcessError."""
        from orchestrator_v3.config import detect_repo_root

        monkeypatch.chdir(tmp_path)

        with patch(
            "orchestrator_v3.config.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ), patch.object(
            Path,
            "exists",
            return_value=False,
        ):
            result = detect_repo_root()
        assert result == Path.cwd()


# ── 2.15 run_env_checks does NOT call doctor-only checks ─────────────


class TestRunEnvChecksExcludesDoctorOnly:
    def test_workflow_does_not_call_doctor_only_checks(self):
        """2.15: run_env_checks for a workflow command does NOT call
        check_python_version, check_required_packages, or check_venv."""
        with patch(
            "orchestrator_v3.env_checks._find_repo_root",
            return_value=Path("/fake/repo"),
        ), patch(
            "orchestrator_v3.env_checks.check_python_version"
        ) as mock_pyver, patch(
            "orchestrator_v3.env_checks.check_required_packages"
        ) as mock_pkgs, patch(
            "orchestrator_v3.env_checks.check_venv"
        ) as mock_venv, patch(
            "shutil.which", return_value="/usr/bin/codex"
        ):
            run_env_checks("plan")

        mock_pyver.assert_not_called()
        mock_pkgs.assert_not_called()
        mock_venv.assert_not_called()


# ── 2.16 / 2.17 doctor exit codes ───────────────────────────────────


class TestDoctorExitCodes:
    @staticmethod
    def _make_result(name: str, status: str) -> EnvCheckResult:
        return EnvCheckResult(name=name, status=status, message=f"{name} {status}")

    def test_doctor_exit_0_all_pass(self):
        """2.16: doctor returns exit code 0 when all checks pass and summary shows counts."""
        from orchestrator_v3.cli import app

        repo = self._make_result("repo_root", "PASS")
        cli = self._make_result("cli:claude", "PASS")
        dir_r = self._make_result("dir:reviews", "PASS")
        pyver = self._make_result("python_version", "PASS")
        pkg = self._make_result("pkg:pydantic", "PASS")
        venv = self._make_result("venv", "PASS")

        with patch(
            "orchestrator_v3.env_checks.check_repo_root",
            return_value=repo,
        ), patch(
            "orchestrator_v3.env_checks.check_cli_tools",
            return_value=[cli],
        ), patch(
            "orchestrator_v3.env_checks._find_repo_root",
            return_value=Path("/fake"),
        ), patch(
            "orchestrator_v3.env_checks.check_directories",
            return_value=[dir_r],
        ), patch(
            "orchestrator_v3.env_checks.check_python_version",
            return_value=pyver,
        ), patch(
            "orchestrator_v3.env_checks.check_required_packages",
            return_value=[pkg],
        ), patch(
            "orchestrator_v3.env_checks.check_venv",
            return_value=venv,
        ):
            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        output = result.output
        # All named checks should appear
        for name in ("repo_root", "cli:claude", "dir:reviews", "python_version",
                     "pkg:pydantic", "venv"):
            assert name in output, f"Check '{name}' missing from doctor output"
        # Summary should reflect exact counts (6 PASS, 0 WARN, 0 FAIL)
        assert "6 passed" in output
        assert "0 warnings" in output
        assert "0 failures" in output

    def test_doctor_exit_1_on_failure(self):
        """2.17: doctor returns exit code 1 when any check FAILs and summary shows failure count."""
        from orchestrator_v3.cli import app

        repo_fail = self._make_result("repo_root", "FAIL")
        repo_fail.fix_hint = "Run from a git repo"
        cli_pass = self._make_result("cli:claude", "PASS")
        dir_pass = self._make_result("dir:reviews", "PASS")
        pyver_pass = self._make_result("python_version", "PASS")
        pkg_pass = self._make_result("pkg:pydantic", "PASS")
        venv_pass = self._make_result("venv", "PASS")

        with patch(
            "orchestrator_v3.env_checks.check_repo_root",
            return_value=repo_fail,
        ), patch(
            "orchestrator_v3.env_checks.check_cli_tools",
            return_value=[cli_pass],
        ), patch(
            "orchestrator_v3.env_checks._find_repo_root",
            return_value=Path("/fake"),
        ), patch(
            "orchestrator_v3.env_checks.check_directories",
            return_value=[dir_pass],
        ), patch(
            "orchestrator_v3.env_checks.check_python_version",
            return_value=pyver_pass,
        ), patch(
            "orchestrator_v3.env_checks.check_required_packages",
            return_value=[pkg_pass],
        ), patch(
            "orchestrator_v3.env_checks.check_venv",
            return_value=venv_pass,
        ):
            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 1
        output = result.output
        # The failed check should appear with FAIL status
        assert "repo_root" in output
        assert "FAIL" in output
        # Summary should reflect exact counts (5 PASS, 0 WARN, 1 FAIL)
        assert "5 passed" in output
        assert "0 warnings" in output
        assert "1 failures" in output
