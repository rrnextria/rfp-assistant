"""Tests for the bootstrap module (venv creation, health checks, error handling).

Phase 1: 11 test requirements covering ensure_venv, reset_venv, uv/fallback
paths, error handling, health validation, and progress messages.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from orchestrator_v3.bootstrap import (
    _create_venv,
    _find_pip,
    _is_venv_healthy,
    _remove_venv,
    _requirements_hash,
    _requirements_stale,
    _venv_python,
    ensure_venv,
    reset_venv,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_how_to(tmp_path: Path) -> Path:
    """Set up a how_to directory with a requirements.txt file."""
    how_to = tmp_path / "how_to"
    pkg_dir = how_to / "orchestrator_v3"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "requirements.txt").write_text("pydantic>=2.0\ntyper>=0.9.0\n")
    return how_to


def _make_healthy_venv(how_to: Path) -> Path:
    """Create a fake .venv directory with a Python binary placeholder and matching requirements hash."""
    venv_dir = how_to / ".venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)
    py = bin_dir / "python"
    py.write_text("#!/fake")
    py.chmod(0o755)
    # Write matching requirements hash so staleness check passes
    stamp = venv_dir / ".requirements_hash"
    stamp.write_text(_requirements_hash(how_to))
    return venv_dir


# ---------------------------------------------------------------------------
# 1.1 ensure_venv creates venv and returns Python path when venv absent
# ---------------------------------------------------------------------------


class TestEnsureVenvCreatesNew:
    @patch("orchestrator_v3.bootstrap._is_venv_healthy")
    @patch("orchestrator_v3.bootstrap._create_venv")
    def test_creates_venv_returns_python_path(self, mock_create, mock_healthy, tmp_path):
        how_to = _make_how_to(tmp_path)
        # venv does not exist yet, _create_venv is mocked so no real creation
        result = ensure_venv(how_to)
        expected = how_to / ".venv" / "bin" / "python"
        assert result == expected
        mock_create.assert_called_once_with(how_to / ".venv", how_to)
        # _is_venv_healthy should not be called because the venv dir doesn't exist
        mock_healthy.assert_not_called()


# ---------------------------------------------------------------------------
# 1.2 ensure_venv returns existing Python path immediately when venv exists
# ---------------------------------------------------------------------------


class TestEnsureVenvExistingHealthy:
    @patch("orchestrator_v3.bootstrap._is_venv_healthy", return_value=True)
    @patch("orchestrator_v3.bootstrap._create_venv")
    def test_returns_immediately_for_healthy_venv(self, mock_create, mock_healthy, tmp_path):
        how_to = _make_how_to(tmp_path)
        _make_healthy_venv(how_to)

        result = ensure_venv(how_to)
        expected = how_to / ".venv" / "bin" / "python"
        assert result == expected
        # Should NOT call _create_venv since venv already healthy
        mock_create.assert_not_called()
        mock_healthy.assert_called_once()


# ---------------------------------------------------------------------------
# 1.3 uv preferred path
# ---------------------------------------------------------------------------


class TestUvPreferredPath:
    @patch("orchestrator_v3.bootstrap.shutil.which", return_value="/usr/bin/uv")
    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_uv_venv_and_pip_install(self, mock_run, mock_which, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_dir = how_to / ".venv"
        venv_dir.mkdir()  # real uv would create this

        _create_venv(venv_dir, how_to)

        assert mock_run.call_count == 2
        # First call: uv venv
        first_call = mock_run.call_args_list[0]
        assert first_call[0][0][0] == "/usr/bin/uv"
        assert first_call[0][0][1] == "venv"
        assert str(venv_dir) in first_call[0][0]

        # Second call: uv pip install
        second_call = mock_run.call_args_list[1]
        assert second_call[0][0][0] == "/usr/bin/uv"
        assert second_call[0][0][1] == "pip"
        assert "install" in second_call[0][0]
        assert "-r" in second_call[0][0]


# ---------------------------------------------------------------------------
# 1.4 Fallback path: no uv, use sys.executable -m venv + pip/ensurepip
# ---------------------------------------------------------------------------


class TestFallbackPathNoUv:
    @patch("orchestrator_v3.bootstrap.shutil.which", return_value=None)
    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_sys_executable_venv_and_pip(self, mock_run, mock_which, tmp_path):
        """When uv is unavailable and pip binary exists, use sys.executable for venv creation."""
        how_to = _make_how_to(tmp_path)
        venv_dir = how_to / ".venv"

        # Create a fake pip binary so _find_pip finds it
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        fake_pip = bin_dir / "pip"
        fake_pip.write_text("#!/fake")
        fake_pip.chmod(0o755)

        _create_venv(venv_dir, how_to)

        # First call: sys.executable -m venv
        first_call = mock_run.call_args_list[0]
        assert first_call[0][0][0] == sys.executable
        assert first_call[0][0][1:3] == ["-m", "venv"]

        # Second call: pip install -r requirements.txt
        second_call = mock_run.call_args_list[1]
        assert str(fake_pip) == second_call[0][0][0]
        assert "install" in second_call[0][0]
        assert "-r" in second_call[0][0]

    @patch("orchestrator_v3.bootstrap.shutil.which", return_value=None)
    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_ensurepip_fallback(self, mock_run, mock_which, tmp_path):
        """When no pip binary exists after venv creation, ensurepip is invoked."""
        how_to = _make_how_to(tmp_path)
        venv_dir = how_to / ".venv"

        # Create bin dir but NO pip binary -- _find_pip returns None
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)

        # After ensurepip is called, simulate pip appearing
        def side_effect(*args, **kwargs):
            cmd = args[0]
            if "-m" in cmd and "ensurepip" in cmd:
                # Simulate ensurepip creating a pip3 binary
                pip3 = bin_dir / "pip3"
                pip3.write_text("#!/fake")
                pip3.chmod(0o755)
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        _create_venv(venv_dir, how_to)

        # Should have 3 calls: venv creation, ensurepip, pip install
        assert mock_run.call_count == 3

        # First: venv creation
        assert mock_run.call_args_list[0][0][0][0] == sys.executable

        # Second: ensurepip
        ensurepip_call = mock_run.call_args_list[1][0][0]
        assert "-m" in ensurepip_call
        assert "ensurepip" in ensurepip_call

        # Third: pip install
        pip_call = mock_run.call_args_list[2][0][0]
        assert "install" in pip_call


# ---------------------------------------------------------------------------
# 1.5 reset_venv deletes existing venv and calls ensure_venv
# ---------------------------------------------------------------------------


class TestResetVenv:
    @patch("orchestrator_v3.bootstrap.ensure_venv")
    @patch("orchestrator_v3.bootstrap._remove_venv")
    def test_reset_deletes_and_recreates(self, mock_remove, mock_ensure, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_dir = _make_healthy_venv(how_to)

        expected_py = how_to / ".venv" / "bin" / "python"
        mock_ensure.return_value = expected_py

        result = reset_venv(how_to)

        mock_remove.assert_called_once_with(venv_dir, how_to)
        mock_ensure.assert_called_once_with(how_to)
        assert result == expected_py

    @patch("orchestrator_v3.bootstrap.ensure_venv")
    def test_reset_no_existing_venv(self, mock_ensure, tmp_path):
        """reset_venv works even when no venv directory exists."""
        how_to = _make_how_to(tmp_path)
        expected_py = how_to / ".venv" / "bin" / "python"
        mock_ensure.return_value = expected_py

        result = reset_venv(how_to)
        # _remove_venv should NOT be called since there's no directory
        mock_ensure.assert_called_once_with(how_to)
        assert result == expected_py


# ---------------------------------------------------------------------------
# 1.6 Error handling: CalledProcessError produces clear message
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @patch("orchestrator_v3.bootstrap.subprocess.run")
    @patch("orchestrator_v3.bootstrap.shutil.which", return_value="/usr/bin/uv")
    def test_called_process_error_message(self, mock_which, mock_run, tmp_path):
        how_to = _make_how_to(tmp_path)
        # First call to subprocess.run (uv venv) raises CalledProcessError
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "uv venv", stderr=b"some error details"
        )

        with pytest.raises(SystemExit) as exc_info:
            ensure_venv(how_to)

        msg = str(exc_info.value)
        assert "Failed to create orchestrator environment" in msg

    @patch("orchestrator_v3.bootstrap.subprocess.run")
    @patch("orchestrator_v3.bootstrap.shutil.which", return_value="/usr/bin/uv")
    def test_pip_not_available_hint(self, mock_which, mock_run, tmp_path):
        how_to = _make_how_to(tmp_path)
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "pip install", stderr=b"No module named pip"
        )

        with pytest.raises(SystemExit) as exc_info:
            ensure_venv(how_to)

        msg = str(exc_info.value)
        assert "pip is not available" in msg
        assert "apt install" in msg

    @patch("orchestrator_v3.bootstrap.subprocess.run")
    @patch("orchestrator_v3.bootstrap.shutil.which", return_value="/usr/bin/uv")
    def test_network_error_hint(self, mock_which, mock_run, tmp_path):
        how_to = _make_how_to(tmp_path)
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "pip install", stderr=b"ConnectionError: name resolution failed"
        )

        with pytest.raises(SystemExit) as exc_info:
            ensure_venv(how_to)

        msg = str(exc_info.value)
        assert "network may be unavailable" in msg


# ---------------------------------------------------------------------------
# 1.7 requirements.txt is read correctly by install command
# ---------------------------------------------------------------------------


class TestRequirementsRead:
    @patch("orchestrator_v3.bootstrap.shutil.which", return_value="/usr/bin/uv")
    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_requirements_path_passed_to_install(self, mock_run, mock_which, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_dir = how_to / ".venv"
        venv_dir.mkdir()  # real uv would create this
        req_file = how_to / "orchestrator_v3" / "requirements.txt"

        _create_venv(venv_dir, how_to)

        # The second subprocess.run call (install) should reference requirements.txt
        install_call = mock_run.call_args_list[1]
        install_args = install_call[0][0]
        assert "-r" in install_args
        r_index = install_args.index("-r")
        assert install_args[r_index + 1] == str(req_file)


# ---------------------------------------------------------------------------
# 1.8 Progress messages are printed during creation
# ---------------------------------------------------------------------------


class TestProgressMessages:
    @patch("orchestrator_v3.bootstrap._create_venv")
    def test_ready_message_on_fresh_create(self, mock_create, tmp_path, capsys):
        how_to = _make_how_to(tmp_path)

        ensure_venv(how_to)

        captured = capsys.readouterr()
        assert "ready" in captured.out.lower()

    @patch("orchestrator_v3.bootstrap.shutil.which", return_value="/usr/bin/uv")
    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_creating_message_uv(self, mock_run, mock_which, tmp_path, capsys):
        how_to = _make_how_to(tmp_path)
        venv_dir = how_to / ".venv"
        venv_dir.mkdir()  # real uv would create this

        _create_venv(venv_dir, how_to)

        captured = capsys.readouterr()
        assert "Creating orchestrator environment" in captured.out
        assert "uv" in captured.out
        assert "Installing dependencies" in captured.out

    @patch("orchestrator_v3.bootstrap.shutil.which", return_value=None)
    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_creating_message_venv(self, mock_run, mock_which, tmp_path, capsys):
        how_to = _make_how_to(tmp_path)
        venv_dir = how_to / ".venv"

        # Need a pip binary so it doesn't go through ensurepip
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        fake_pip = bin_dir / "pip"
        fake_pip.write_text("#!/fake")
        fake_pip.chmod(0o755)

        _create_venv(venv_dir, how_to)

        captured = capsys.readouterr()
        assert "Creating orchestrator environment" in captured.out
        assert "venv" in captured.out
        assert "Installing dependencies" in captured.out


# ---------------------------------------------------------------------------
# 1.9 ensure_venv auto-recreates when import validation fails
# ---------------------------------------------------------------------------


class TestAutoRecreateOnFailedImport:
    @patch("orchestrator_v3.bootstrap._create_venv")
    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_recreates_when_import_probe_fails(self, mock_run, mock_create, tmp_path, capsys):
        how_to = _make_how_to(tmp_path)
        venv_dir = _make_healthy_venv(how_to)

        # The import probe returns non-zero (unhealthy)
        mock_run.return_value = MagicMock(returncode=1)

        result = ensure_venv(how_to)

        captured = capsys.readouterr()
        assert "unhealthy" in captured.out.lower()

        # _remove_venv should have deleted the old venv before recreating
        assert not venv_dir.exists(), "Old venv should be deleted before recreation"

        # _create_venv called to rebuild
        mock_create.assert_called_once_with(how_to / ".venv", how_to)
        assert result == _venv_python(how_to / ".venv")


# ---------------------------------------------------------------------------
# 1.10 PermissionError during venv creation
# ---------------------------------------------------------------------------


class TestPermissionError:
    @patch("orchestrator_v3.bootstrap._create_venv")
    def test_permission_error_clear_message(self, mock_create, tmp_path):
        how_to = _make_how_to(tmp_path)
        mock_create.side_effect = PermissionError("Permission denied: /restricted")

        with pytest.raises(SystemExit) as exc_info:
            ensure_venv(how_to)

        msg = str(exc_info.value)
        assert "Permission denied" in msg
        assert "creating orchestrator environment" in msg.lower()
        assert str(how_to) in msg


# ---------------------------------------------------------------------------
# 1.11 Auto-recreates when venv Python binary is missing
# ---------------------------------------------------------------------------


class TestAutoRecreateOnMissingBinary:
    @patch("orchestrator_v3.bootstrap._create_venv")
    def test_recreates_when_python_binary_missing(self, mock_create, tmp_path, capsys):
        how_to = _make_how_to(tmp_path)
        # Create venv dir but WITHOUT the python binary
        venv_dir = how_to / ".venv"
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        # Write matching stamp so staleness doesn't mask the health issue
        (venv_dir / ".requirements_hash").write_text(_requirements_hash(how_to))
        # bin/python does NOT exist

        result = ensure_venv(how_to)

        captured = capsys.readouterr()
        assert "unhealthy" in captured.out.lower()

        # _remove_venv should have deleted the old venv before recreating
        assert not venv_dir.exists(), "Old venv should be deleted before recreation"

        # _create_venv should be called to rebuild
        mock_create.assert_called_once_with(venv_dir, how_to)
        assert result == _venv_python(venv_dir)


# ---------------------------------------------------------------------------
# Extra: _find_pip, _is_venv_healthy, _remove_venv unit tests
# ---------------------------------------------------------------------------


class TestFindPip:
    def test_finds_pip_binary(self, tmp_path):
        venv_dir = tmp_path / ".venv"
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        pip = bin_dir / "pip"
        pip.write_text("#!/fake")
        pip.chmod(0o755)

        result = _find_pip(venv_dir)
        assert result == str(pip)

    def test_finds_pip3_fallback(self, tmp_path):
        venv_dir = tmp_path / ".venv"
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        pip3 = bin_dir / "pip3"
        pip3.write_text("#!/fake")
        pip3.chmod(0o755)

        result = _find_pip(venv_dir)
        assert result == str(pip3)

    def test_returns_none_when_no_pip(self, tmp_path):
        venv_dir = tmp_path / ".venv"
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)

        result = _find_pip(venv_dir)
        assert result is None


class TestIsVenvHealthy:
    def test_unhealthy_when_no_python(self, tmp_path):
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        assert not _is_venv_healthy(venv_dir)

    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_healthy_when_import_succeeds(self, mock_run, tmp_path):
        venv_dir = tmp_path / ".venv"
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        py = bin_dir / "python"
        py.write_text("#!/fake")
        py.chmod(0o755)

        mock_run.return_value = MagicMock(returncode=0)
        assert _is_venv_healthy(venv_dir) is True

    @patch("orchestrator_v3.bootstrap.subprocess.run")
    def test_unhealthy_when_import_fails(self, mock_run, tmp_path):
        venv_dir = tmp_path / ".venv"
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        py = bin_dir / "python"
        py.write_text("#!/fake")
        py.chmod(0o755)

        mock_run.return_value = MagicMock(returncode=1)
        assert _is_venv_healthy(venv_dir) is False


class TestRemoveVenv:
    def test_removes_directory(self, tmp_path):
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "file.txt").write_text("data")

        _remove_venv(venv_dir, tmp_path)
        assert not venv_dir.exists()

    @patch("orchestrator_v3.bootstrap.shutil.rmtree")
    def test_permission_error_raises_system_exit(self, mock_rmtree, tmp_path):
        venv_dir = tmp_path / ".venv"
        how_to = tmp_path
        mock_rmtree.side_effect = PermissionError("denied")

        with pytest.raises(SystemExit) as exc_info:
            _remove_venv(venv_dir, how_to)

        msg = str(exc_info.value)
        assert "Permission denied" in msg


# ---------------------------------------------------------------------------
# Requirements hash stamp
# ---------------------------------------------------------------------------


class TestRequirementsHash:
    def test_hash_is_deterministic(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        h1 = _requirements_hash(how_to)
        h2 = _requirements_hash(how_to)
        assert h1 == h2
        assert len(h1) == 16  # first 16 hex chars

    def test_hash_changes_with_content(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        h1 = _requirements_hash(how_to)
        req = how_to / "orchestrator_v3" / "requirements.txt"
        req.write_text("pydantic>=2.0\ntyper>=0.9.0\nnew-dep>=1.0\n")
        h2 = _requirements_hash(how_to)
        assert h1 != h2

    def test_stale_when_no_stamp(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_dir = how_to / ".venv"
        venv_dir.mkdir()
        assert _requirements_stale(venv_dir, how_to) is True

    def test_not_stale_when_stamp_matches(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_dir = how_to / ".venv"
        venv_dir.mkdir()
        stamp = venv_dir / ".requirements_hash"
        stamp.write_text(_requirements_hash(how_to))
        assert _requirements_stale(venv_dir, how_to) is False

    def test_stale_when_stamp_mismatches(self, tmp_path):
        how_to = _make_how_to(tmp_path)
        venv_dir = how_to / ".venv"
        venv_dir.mkdir()
        stamp = venv_dir / ".requirements_hash"
        stamp.write_text("old_hash_value_xx")
        assert _requirements_stale(venv_dir, how_to) is True


class TestEnsureVenvStaleness:
    @patch("orchestrator_v3.bootstrap._create_venv")
    @patch("orchestrator_v3.bootstrap._is_venv_healthy", return_value=True)
    def test_stale_venv_is_recreated(self, mock_healthy, mock_create, tmp_path):
        """A healthy venv with stale requirements hash is rebuilt."""
        how_to = _make_how_to(tmp_path)
        venv_dir = _make_healthy_venv(how_to)
        # Write a mismatched stamp
        (venv_dir / ".requirements_hash").write_text("stale_hash_value")

        ensure_venv(how_to)

        # Old venv should have been deleted
        assert not venv_dir.exists()
        # _create_venv should have been called to rebuild
        mock_create.assert_called_once()

    @patch("orchestrator_v3.bootstrap._create_venv")
    @patch("orchestrator_v3.bootstrap._is_venv_healthy", return_value=True)
    def test_fresh_venv_is_kept(self, mock_healthy, mock_create, tmp_path):
        """A healthy venv with matching requirements hash is kept."""
        how_to = _make_how_to(tmp_path)
        venv_dir = _make_healthy_venv(how_to)
        # Write a matching stamp
        (venv_dir / ".requirements_hash").write_text(_requirements_hash(how_to))

        result = ensure_venv(how_to)

        # _create_venv should NOT be called
        mock_create.assert_not_called()
        assert result == _venv_python(venv_dir)
