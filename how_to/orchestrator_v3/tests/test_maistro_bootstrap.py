"""Tests for maistro/ directory bootstrap and .gitignore auto-append."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestBootstrapMaistroDirs:
    """Test _bootstrap_maistro_dirs creates dirs and updates .gitignore."""

    def test_creates_sessions_dir(self, tmp_path):
        """Bootstrap creates maistro/sessions/ at repo root."""
        from orchestrator_v3.cli import _bootstrap_maistro_dirs

        (tmp_path / ".git").mkdir()
        with patch("orchestrator_v3.config.detect_repo_root", return_value=tmp_path):
            _bootstrap_maistro_dirs()

        assert (tmp_path / "maistro" / "sessions").is_dir()

    def test_appends_to_existing_gitignore(self, tmp_path):
        """Bootstrap appends maistro/ to existing .gitignore."""
        from orchestrator_v3.cli import _bootstrap_maistro_dirs

        (tmp_path / ".git").mkdir()
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n")

        with patch("orchestrator_v3.config.detect_repo_root", return_value=tmp_path):
            _bootstrap_maistro_dirs()

        content = gitignore.read_text()
        assert "maistro/" in content
        assert "*.pyc" in content

    def test_creates_gitignore_if_missing(self, tmp_path):
        """Bootstrap creates .gitignore with maistro/ if it doesn't exist."""
        from orchestrator_v3.cli import _bootstrap_maistro_dirs

        (tmp_path / ".git").mkdir()

        with patch("orchestrator_v3.config.detect_repo_root", return_value=tmp_path):
            _bootstrap_maistro_dirs()

        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert "maistro/" in gitignore.read_text()

    def test_idempotent_gitignore(self, tmp_path):
        """Calling bootstrap twice does not duplicate the maistro/ entry."""
        from orchestrator_v3.cli import _bootstrap_maistro_dirs

        (tmp_path / ".git").mkdir()
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n")

        with patch("orchestrator_v3.config.detect_repo_root", return_value=tmp_path):
            _bootstrap_maistro_dirs()
            _bootstrap_maistro_dirs()

        content = gitignore.read_text()
        assert content.count("maistro/") == 1

    def test_does_not_duplicate_if_already_present(self, tmp_path):
        """If .gitignore already has maistro/, don't add it again."""
        from orchestrator_v3.cli import _bootstrap_maistro_dirs

        (tmp_path / ".git").mkdir()
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\nmaistro/\n")

        with patch("orchestrator_v3.config.detect_repo_root", return_value=tmp_path):
            _bootstrap_maistro_dirs()

        content = gitignore.read_text()
        assert content.count("maistro/") == 1

    def test_sessions_dir_idempotent(self, tmp_path):
        """Calling bootstrap when maistro/sessions/ exists doesn't fail."""
        from orchestrator_v3.cli import _bootstrap_maistro_dirs

        (tmp_path / ".git").mkdir()
        (tmp_path / "maistro" / "sessions").mkdir(parents=True)

        with patch("orchestrator_v3.config.detect_repo_root", return_value=tmp_path):
            _bootstrap_maistro_dirs()

        assert (tmp_path / "maistro" / "sessions").is_dir()


class TestEnvChecksIncludesMaistro:
    """Test that env_checks.check_directories includes maistro/."""

    def test_check_directories_includes_maistro(self, tmp_path):
        """check_directories should check for maistro/ directory."""
        from orchestrator_v3.env_checks import check_directories

        results = check_directories(tmp_path)
        names = [r.name for r in results]
        assert "dir:maistro" in names

    def test_check_directories_maistro_warn_when_missing(self, tmp_path):
        """maistro/ missing should produce a WARN status."""
        from orchestrator_v3.env_checks import check_directories

        results = check_directories(tmp_path)
        maistro_result = [r for r in results if r.name == "dir:maistro"][0]
        assert maistro_result.status == "WARN"

    def test_check_directories_maistro_pass_when_present(self, tmp_path):
        """maistro/ present should produce a PASS status."""
        from orchestrator_v3.env_checks import check_directories

        (tmp_path / "maistro").mkdir()
        results = check_directories(tmp_path)
        maistro_result = [r for r in results if r.name == "dir:maistro"][0]
        assert maistro_result.status == "PASS"


class TestAppCallback:
    """Test that the Typer app callback triggers bootstrap."""

    def test_help_does_not_crash(self):
        """App --help should work with the callback in place."""
        from typer.testing import CliRunner

        from orchestrator_v3.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "plan" in result.output

    def test_plan_help_does_not_create_maistro(self, tmp_path):
        """plan --help should not create maistro/ or modify .gitignore.

        Bootstrap is now called inside each command body (not a callback),
        so --help never reaches the bootstrap call.
        """
        from typer.testing import CliRunner

        from orchestrator_v3.cli import app

        (tmp_path / ".git").mkdir()
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n")

        with patch("orchestrator_v3.config.detect_repo_root", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(app, ["plan", "--help"])

        assert result.exit_code == 0
        assert not (tmp_path / "maistro").exists(), "plan --help should not create maistro/"
        assert "maistro/" not in gitignore.read_text(), "plan --help should not modify .gitignore"
