"""Tests for RunRecorder context manager, UUID generation, hashing, git capture, and summary emission."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from unittest.mock import patch

import pytest


class TestUUID7:
    """Test UUIDv7 generation."""

    def test_format(self):
        from orchestrator_v3.run_recorder import _uuid7

        uid = _uuid7()
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            uid,
        ), f"Invalid UUIDv7 format: {uid}"

    def test_timestamp_prefix_stable(self):
        from orchestrator_v3.run_recorder import _uuid7

        a = _uuid7()
        b = _uuid7()
        # Same millisecond → same 12-char timestamp prefix (48-bit timestamp)
        # Different millisecond → b sorts after a
        assert b[:13] >= a[:13]  # Compare up to first dash + 4 hex chars

    def test_unique(self):
        from orchestrator_v3.run_recorder import _uuid7

        ids = {_uuid7() for _ in range(100)}
        assert len(ids) == 100


class TestSHA256:
    """Test file hashing utilities."""

    def test_sha256_file(self, tmp_path):
        from orchestrator_v3.run_recorder import sha256_file

        f = tmp_path / "test.txt"
        f.write_text("hello world\n")
        digest = sha256_file(f)
        assert len(digest) == 64
        assert re.match(r"^[0-9a-f]{64}$", digest)

    def test_sha256_deterministic(self, tmp_path):
        from orchestrator_v3.run_recorder import sha256_file

        f = tmp_path / "test.txt"
        f.write_text("deterministic content")
        assert sha256_file(f) == sha256_file(f)

    def test_hash_files_skips_missing(self, tmp_path):
        from orchestrator_v3.run_recorder import hash_files

        existing = tmp_path / "exists.txt"
        existing.write_text("content")
        missing = tmp_path / "missing.txt"

        result = hash_files([existing, missing])
        assert str(existing) in result
        assert str(missing) not in result

    def test_hash_files_skips_dirs(self, tmp_path):
        from orchestrator_v3.run_recorder import hash_files

        d = tmp_path / "subdir"
        d.mkdir()
        result = hash_files([d])
        assert len(result) == 0


class TestGitState:
    """Test git state capture."""

    def test_capture_git_state_real(self, tmp_path):
        """capture_git_state returns valid state when run in a real git repo."""
        from orchestrator_v3.run_recorder import capture_git_state

        # This test runs from the OrchestratorV3 repo, so git should work
        state = capture_git_state()
        assert len(state.sha) == 40 or state.sha == "unknown"
        assert state.branch != ""

    def test_capture_git_state_fallback(self, tmp_path):
        """Falls back to defaults when git commands fail."""
        from orchestrator_v3.run_recorder import capture_git_state

        with patch("orchestrator_v3.run_recorder.subprocess.run", side_effect=FileNotFoundError):
            state = capture_git_state(tmp_path)
        assert state.sha == "unknown"
        assert state.branch == "unknown"
        assert state.dirty is False

    def test_capture_git_state_timeout(self, tmp_path):
        """Falls back to defaults on timeout."""
        import subprocess as sp

        from orchestrator_v3.run_recorder import capture_git_state

        with patch("orchestrator_v3.run_recorder.subprocess.run", side_effect=sp.TimeoutExpired("git", 5)):
            state = capture_git_state(tmp_path)
        assert state.sha == "unknown"


class TestRunRecorder:
    """Test RunRecorder context manager protocol."""

    def test_enter_populates_fields(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        (tmp_path / ".git").mkdir()
        recorder = RunRecorder(mode="plan", slug="test_slug", repo_root=tmp_path)

        with recorder:
            assert recorder.run_id != ""
            assert recorder.start_time > 0
            assert recorder.mode == "plan"
            assert recorder.slug == "test_slug"

    def test_exit_sets_end_time(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="code", slug="s", repo_root=tmp_path, phase=0, task=1)
        with recorder:
            recorder.outcome = "approved"

        assert recorder.end_time > 0
        assert recorder.end_time >= recorder.start_time

    def test_duration(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with recorder:
            time.sleep(0.01)
            recorder.outcome = "approved"

        assert recorder.duration >= 0.01

    def test_outcome_defaults_to_unknown(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with recorder:
            pass  # Don't set outcome

        assert recorder.outcome == "unknown"

    def test_outcome_set_to_error_on_exception(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with pytest.raises(ValueError):
            with recorder:
                raise ValueError("test error")

        assert recorder.outcome == "error"
        assert recorder.end_time > 0

    def test_exception_not_suppressed(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with pytest.raises(RuntimeError, match="boom"):
            with recorder:
                raise RuntimeError("boom")

    def test_add_artifact(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with recorder:
            recorder.add_artifact("/path/to/review.md")
            recorder.add_artifact(Path("/path/to/code.py"))

        assert len(recorder.artifact_paths) == 2
        assert "/path/to/review.md" in recorder.artifact_paths

    def test_phase_task_for_code_mode(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="code", slug="s", repo_root=tmp_path, phase=2, task=3)
        assert recorder.phase == 2
        assert recorder.task == 3

    def test_phase_task_none_for_plan_mode(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        assert recorder.phase is None
        assert recorder.task is None

    def test_hashes_project_files(self, tmp_path):
        """RunRecorder hashes guides, templates, and prompts."""
        from orchestrator_v3.run_recorder import RunRecorder

        how_to = tmp_path / "how_to"
        guides = how_to / "guides"
        guides.mkdir(parents=True)
        (guides / "setup.md").write_text("setup guide")
        templates = how_to / "templates"
        templates.mkdir()
        (templates / "phase.md").write_text("phase template")
        orch = how_to / "orchestrator_v3"
        orch.mkdir()
        (orch / "prompts.py").write_text("prompt code")

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with recorder:
            pass

        assert len(recorder.file_hashes) == 3
        assert any("setup.md" in k for k in recorder.file_hashes)
        assert any("phase.md" in k for k in recorder.file_hashes)
        assert any("prompts.py" in k for k in recorder.file_hashes)

    def test_git_state_captured(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with patch("orchestrator_v3.run_recorder.capture_git_state") as mock_git:
            from orchestrator_v3.run_recorder import GitState

            mock_git.return_value = GitState(sha="abc123", branch="main", dirty=False)
            recorder.__enter__()
            recorder.__exit__(None, None, None)

        assert recorder.git_state.sha == "abc123"
        assert recorder.git_state.branch == "main"


class TestSummaryEmission:
    """Test run_summary.json emission in RunRecorder.__exit__."""

    def test_summary_emitted_on_normal_exit(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="test_slug", repo_root=tmp_path)
        with recorder:
            recorder.outcome = "approved"

        sessions_dir = tmp_path / "maistro" / "sessions"
        summary_path = sessions_dir / f"{recorder.run_id}_summary.json"
        assert summary_path.exists()
        data = json.loads(summary_path.read_text())
        assert data["run_id"] == recorder.run_id
        assert data["mode"] == "plan"
        assert data["slug"] == "test_slug"
        assert data["outcome"] == "approved"
        assert data["duration_seconds"] >= 0
        assert data["start_time"] is not None
        assert data["end_time"] is not None

    def test_summary_emitted_on_error(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with pytest.raises(ValueError):
            with recorder:
                raise ValueError("boom")

        sessions_dir = tmp_path / "maistro" / "sessions"
        summary_path = sessions_dir / f"{recorder.run_id}_summary.json"
        assert summary_path.exists()
        data = json.loads(summary_path.read_text())
        assert data["outcome"] == "error"

    def test_summary_contains_git_state(self, tmp_path):
        from orchestrator_v3.run_recorder import GitState, RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with patch("orchestrator_v3.run_recorder.capture_git_state") as mock_git:
            mock_git.return_value = GitState(sha="abc123", branch="main", dirty=True)
            with recorder:
                recorder.outcome = "approved"

        data = json.loads(
            (tmp_path / "maistro" / "sessions" / f"{recorder.run_id}_summary.json").read_text()
        )
        assert data["git_state"]["sha"] == "abc123"
        assert data["git_state"]["branch"] == "main"
        assert data["git_state"]["dirty"] is True

    def test_summary_contains_verdict_history_for_plan(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with recorder:
            recorder.outcome = "approved"
            recorder.set_verdict_history([
                {"round": 1, "action": "review", "verdict": "FIXES_REQUIRED", "blocker": 0, "major": 2, "minor": 1},
                {"round": 2, "action": "review", "verdict": "APPROVED", "blocker": 0, "major": 0, "minor": 0},
            ])

        data = json.loads(
            (tmp_path / "maistro" / "sessions" / f"{recorder.run_id}_summary.json").read_text()
        )
        assert data["verdict_history"] is not None
        assert len(data["verdict_history"]) == 2
        assert data["total_rounds"] == 2

    def test_summary_contains_convergence_for_research(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="research", slug="s", repo_root=tmp_path)
        with recorder:
            recorder.outcome = "complete"
            recorder.set_convergence_data(
                rounds=2,
                opus_agreement=9,
                codex_agreement=8,
                open_issues=0,
                final_status="complete",
                history=[{"phase": 1, "model": "opus", "action": "initial"}],
            )

        data = json.loads(
            (tmp_path / "maistro" / "sessions" / f"{recorder.run_id}_summary.json").read_text()
        )
        assert "convergence" in data
        assert data["convergence"]["rounds"] == 2
        assert data["convergence"]["opus_agreement"] == 9
        assert data["convergence"]["codex_agreement"] == 8
        assert data["convergence"]["open_issues"] == 0
        # Research mode should not have verdict_history
        assert "verdict_history" not in data

    def test_summary_contains_finding_counts_from_orch_meta(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        # Create a review artifact with ORCH_META
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()
        review_file = reviews_dir / "slug_plan_review_round1.md"
        review_file.write_text(
            "<!-- ORCH_META\nVERDICT: FIXES_REQUIRED\nBLOCKER: 0\n"
            "MAJOR: 2\nMINOR: 1\nDECISIONS: 0\nVERIFIED: 0\n-->\n\n# Review\n"
        )

        recorder = RunRecorder(mode="plan", slug="slug", repo_root=tmp_path)
        with recorder:
            recorder.outcome = "needs_response"
            recorder.add_artifact(str(review_file))

        data = json.loads(
            (tmp_path / "maistro" / "sessions" / f"{recorder.run_id}_summary.json").read_text()
        )
        assert len(data["finding_counts"]) == 1
        assert data["finding_counts"][0]["verdict"] == "FIXES_REQUIRED"
        assert data["finding_counts"][0]["major"] == 2
        assert data["finding_counts"][0]["minor"] == 1
        assert data["total_findings"]["major"] == 2

    def test_summary_skips_non_review_artifacts(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with recorder:
            recorder.outcome = "approved"
            recorder.add_artifact("/path/to/code_complete_round1.md")

        data = json.loads(
            (tmp_path / "maistro" / "sessions" / f"{recorder.run_id}_summary.json").read_text()
        )
        assert data["finding_counts"] == []

    def test_summary_code_mode_includes_phase_task(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="code", slug="s", repo_root=tmp_path, phase=2, task=3)
        with recorder:
            recorder.outcome = "approved"

        data = json.loads(
            (tmp_path / "maistro" / "sessions" / f"{recorder.run_id}_summary.json").read_text()
        )
        assert data["phase"] == 2
        assert data["task"] == 3

    def test_summary_file_hashes_included(self, tmp_path):
        from orchestrator_v3.run_recorder import RunRecorder

        how_to = tmp_path / "how_to"
        guides = how_to / "guides"
        guides.mkdir(parents=True)
        (guides / "setup.md").write_text("setup guide")

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with recorder:
            recorder.outcome = "approved"

        data = json.loads(
            (tmp_path / "maistro" / "sessions" / f"{recorder.run_id}_summary.json").read_text()
        )
        assert len(data["file_hashes"]) == 1
        assert any("setup.md" in k for k in data["file_hashes"])


class TestSessionDiscovery:
    """Test Claude session transcript discovery."""

    def test_encode_project_path(self):
        from orchestrator_v3.run_recorder import encode_project_path

        result = encode_project_path(Path("/home/user/git/MyRepo"))
        assert result == "-home-user-git-MyRepo"

    def test_discover_matching_session(self, tmp_path):
        from orchestrator_v3.run_recorder import discover_session_files

        # Set up mock Claude directory structure
        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-tmp-repo"
        project_dir.mkdir(parents=True)

        repo_root = Path("/tmp/repo")
        now = time.time()

        # Create a JSONL file with mtime in the run window
        session = project_dir / "abc123.jsonl"
        session.write_text('{"test": true}\n')
        os.utime(session, (now, now))

        results = discover_session_files(
            repo_root, start_time=now - 10, end_time=now + 10,
            claude_dir=claude_dir,
        )
        assert len(results) == 1
        assert results[0] == session

    def test_discover_filters_by_time(self, tmp_path):
        from orchestrator_v3.run_recorder import discover_session_files

        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-tmp-repo"
        project_dir.mkdir(parents=True)

        repo_root = Path("/tmp/repo")
        now = time.time()

        # Session outside the run window (too old)
        old_session = project_dir / "old.jsonl"
        old_session.write_text('{"test": true}\n')
        os.utime(old_session, (now - 3600, now - 3600))

        results = discover_session_files(
            repo_root, start_time=now - 10, end_time=now + 10,
            claude_dir=claude_dir,
        )
        assert len(results) == 0

    def test_discover_no_project_dir(self, tmp_path):
        from orchestrator_v3.run_recorder import discover_session_files

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        results = discover_session_files(
            Path("/tmp/repo"), start_time=time.time() - 10, end_time=time.time(),
            claude_dir=claude_dir,
        )
        assert results == []

    def test_discover_multiple_sessions_sorted(self, tmp_path):
        from orchestrator_v3.run_recorder import discover_session_files

        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-tmp-repo"
        project_dir.mkdir(parents=True)

        repo_root = Path("/tmp/repo")
        now = time.time()

        s1 = project_dir / "session1.jsonl"
        s1.write_text('{"test": 1}\n')
        os.utime(s1, (now - 5, now - 5))

        s2 = project_dir / "session2.jsonl"
        s2.write_text('{"test": 2}\n')
        os.utime(s2, (now, now))

        results = discover_session_files(
            repo_root, start_time=now - 10, end_time=now + 10,
            claude_dir=claude_dir,
        )
        assert len(results) == 2
        # Newest first
        assert results[0] == s2
        assert results[1] == s1

    def test_discover_sessions_index_fallback(self, tmp_path):
        import json as _json

        from orchestrator_v3.run_recorder import discover_session_files

        claude_dir = tmp_path / ".claude"
        # Create project dir but no JSONL files (primary method fails)
        project_dir = claude_dir / "projects" / "-tmp-repo"
        project_dir.mkdir(parents=True)

        now = time.time()

        # Create a session file referenced by the index
        session_file = project_dir / "abc123.jsonl"
        session_file.write_text('{"test": true}\n')
        os.utime(session_file, (now, now))

        # Create per-project sessions-index.json with real schema
        index_path = project_dir / "sessions-index.json"
        index_path.write_text(_json.dumps({
            "version": 1,
            "originalPath": "/tmp/repo",
            "entries": [
                {
                    "sessionId": "abc123",
                    "fullPath": str(session_file),
                    "projectPath": "/tmp/repo",
                },
            ],
        }))

        # Remove the JSONL from glob range so primary scan fails
        # (set mtime far in the past so primary scan misses it)
        os.utime(session_file, (now - 7200, now - 7200))

        # But the index fallback should still find it (it re-checks mtime)
        # Actually, we need the file mtime in range for fallback too.
        # So: have NO jsonl in the project dir for primary, put session elsewhere.

        # Better approach: remove the jsonl, create the index pointing to a different location
        session_file.unlink()
        alt_session = tmp_path / "alt_session.jsonl"
        alt_session.write_text('{"test": true}\n')
        os.utime(alt_session, (now, now))
        index_path.write_text(_json.dumps({
            "version": 1,
            "originalPath": "/tmp/repo",
            "entries": [
                {
                    "sessionId": "def456",
                    "fullPath": str(alt_session),
                    "projectPath": "/tmp/repo",
                },
            ],
        }))

        results = discover_session_files(
            Path("/tmp/repo"), start_time=now - 10, end_time=now + 10,
            claude_dir=claude_dir,
        )
        assert len(results) == 1
        assert results[0] == alt_session

    def test_discover_index_rejects_wrong_project(self, tmp_path):
        import json as _json

        from orchestrator_v3.run_recorder import discover_session_files

        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-tmp-repo"
        project_dir.mkdir(parents=True)

        now = time.time()
        session_file = tmp_path / "foreign.jsonl"
        session_file.write_text('{"test": true}\n')
        os.utime(session_file, (now, now))

        # Index entry points to a different repo
        index_path = project_dir / "sessions-index.json"
        index_path.write_text(_json.dumps({
            "version": 1,
            "originalPath": "/other/repo",
            "entries": [
                {
                    "sessionId": "xyz",
                    "fullPath": str(session_file),
                    "projectPath": "/other/repo",
                },
            ],
        }))

        results = discover_session_files(
            Path("/tmp/repo"), start_time=now - 10, end_time=now + 10,
            claude_dir=claude_dir,
        )
        assert len(results) == 0

    def test_discover_index_rejects_wrong_original_path(self, tmp_path):
        """Top-level originalPath mismatch rejects entries lacking projectPath."""
        import json as _json

        from orchestrator_v3.run_recorder import discover_session_files

        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-tmp-repo"
        project_dir.mkdir(parents=True)

        now = time.time()
        session_file = tmp_path / "foreign.jsonl"
        session_file.write_text('{"test": true}\n')
        os.utime(session_file, (now, now))

        # Entry has no projectPath; top-level originalPath is a different repo
        index_path = project_dir / "sessions-index.json"
        index_path.write_text(_json.dumps({
            "version": 1,
            "originalPath": "/other/repo",
            "entries": [
                {
                    "sessionId": "xyz",
                    "fullPath": str(session_file),
                },
            ],
        }))

        results = discover_session_files(
            Path("/tmp/repo"), start_time=now - 10, end_time=now + 10,
            claude_dir=claude_dir,
        )
        assert len(results) == 0

    def test_discover_index_rejects_missing_project_paths(self, tmp_path):
        """Index with no originalPath and no per-entry projectPath rejects all entries."""
        import json as _json

        from orchestrator_v3.run_recorder import discover_session_files

        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-tmp-repo"
        project_dir.mkdir(parents=True)

        now = time.time()
        session_file = tmp_path / "orphan.jsonl"
        session_file.write_text('{"test": true}\n')
        os.utime(session_file, (now, now))

        # Index omits both originalPath and per-entry projectPath
        index_path = project_dir / "sessions-index.json"
        index_path.write_text(_json.dumps({
            "version": 1,
            "entries": [
                {
                    "sessionId": "xyz",
                    "fullPath": str(session_file),
                },
            ],
        }))

        results = discover_session_files(
            Path("/tmp/repo"), start_time=now - 10, end_time=now + 10,
            claude_dir=claude_dir,
        )
        assert len(results) == 0

    def test_discover_malformed_index(self, tmp_path):
        from orchestrator_v3.run_recorder import discover_session_files

        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-tmp-repo"
        project_dir.mkdir(parents=True)

        index_path = project_dir / "sessions-index.json"
        index_path.write_text("not valid json{{{")

        results = discover_session_files(
            Path("/tmp/repo"), start_time=time.time() - 10, end_time=time.time(),
            claude_dir=claude_dir,
        )
        assert results == []

    def test_recorder_discovers_sessions(self, tmp_path):
        """RunRecorder populates session_paths on exit."""
        from orchestrator_v3.run_recorder import RunRecorder, encode_project_path

        claude_dir = tmp_path / ".claude_test"
        encoded = encode_project_path(tmp_path)
        project_dir = claude_dir / "projects" / encoded
        project_dir.mkdir(parents=True)

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with patch("orchestrator_v3.run_recorder.discover_session_files") as mock_discover:
            session = project_dir / "test.jsonl"
            session.write_text("{}\n")
            mock_discover.return_value = [session]
            with recorder:
                recorder.outcome = "approved"

        assert len(recorder.session_paths) == 1

    def test_summary_includes_session_paths(self, tmp_path):
        """run_summary.json includes session_paths field."""
        from orchestrator_v3.run_recorder import RunRecorder

        recorder = RunRecorder(mode="plan", slug="s", repo_root=tmp_path)
        with patch("orchestrator_v3.run_recorder.discover_session_files", return_value=[]):
            with recorder:
                recorder.outcome = "approved"

        data = json.loads(
            (tmp_path / "maistro" / "sessions" / f"{recorder.run_id}_summary.json").read_text()
        )
        assert "session_paths" in data
        assert data["session_paths"] == []


class TestSessionArchive:
    """Test session archive builder."""

    def test_plan_archive_structure(self, tmp_path):
        """Plan mode archive contains artifacts/reviews/, run/, manifest.json, meta.json."""
        import tarfile as _tarfile

        from orchestrator_v3.run_recorder import RunRecorder

        repo = tmp_path / "repo"
        repo.mkdir()
        reviews = repo / "reviews"
        reviews.mkdir()

        # Create slug-filtered review artifacts
        (reviews / "myslug_plan_review_round1.md").write_text("# Review\n")
        (reviews / "myslug_plan_review_round1.md.log").write_text("log\n")
        (reviews / "other_plan_review_round1.md").write_text("# Other\n")
        # Create orchestrator state file (real naming convention)
        (reviews / "myslug_orchestrator_state.json").write_text('{"status":"approved"}\n')

        # Create plan snapshot (simple plan naming convention)
        (repo / "active_plans").mkdir(parents=True)
        (repo / "active_plans" / "myslug.md").write_text("# Plan\n")

        with patch("orchestrator_v3.run_recorder.discover_session_files", return_value=[]):
            recorder = RunRecorder(mode="plan", slug="myslug", repo_root=repo)
            with recorder:
                recorder.outcome = "approved"

        # Find the archive
        sessions = repo / "maistro" / "sessions"
        archives = list(sessions.glob("*.tar.gz"))
        assert len(archives) == 1
        archive = archives[0]
        assert "_plan_myslug_" in archive.name
        assert recorder.archive_path == str(archive)

        with _tarfile.open(archive, "r:gz") as tf:
            names = tf.getnames()

        assert "manifest.json" in names
        assert "meta.json" in names
        assert "artifacts/reviews/myslug_plan_review_round1.md" in names
        assert "artifacts/reviews/myslug_plan_review_round1.md.log" in names
        assert "run/state.json" in names
        assert "run/plan_snapshot.md" in names
        assert "run/run_summary.json" in names
        # Other slug's artifacts must NOT be included
        assert "artifacts/reviews/other_plan_review_round1.md" not in names

    def test_research_archive_structure(self, tmp_path):
        """Research mode archive contains artifacts/research/ from research/<slug>/."""
        import tarfile as _tarfile

        from orchestrator_v3.run_recorder import RunRecorder

        repo = tmp_path / "repo"
        repo.mkdir()

        # Create research artifacts
        rdir = repo / "research" / "myresearch"
        rdir.mkdir(parents=True)
        (rdir / "opus_initial.md").write_text("# Opus\n")
        logs = rdir / "logs"
        logs.mkdir()
        (logs / "opus.log").write_text("log\n")

        with patch("orchestrator_v3.run_recorder.discover_session_files", return_value=[]):
            recorder = RunRecorder(mode="research", slug="myresearch", repo_root=repo)
            with recorder:
                recorder.outcome = "complete"

        sessions = repo / "maistro" / "sessions"
        archives = list(sessions.glob("*.tar.gz"))
        assert len(archives) == 1

        with _tarfile.open(archives[0], "r:gz") as tf:
            names = tf.getnames()

        assert "manifest.json" in names
        assert "meta.json" in names
        assert "artifacts/research/opus_initial.md" in names
        assert "artifacts/research/logs/opus.log" in names

    def test_manifest_hashes_match(self, tmp_path):
        """Manifest SHA-256 hashes must match actual file contents."""
        import tarfile as _tarfile

        from orchestrator_v3.run_recorder import RunRecorder, sha256_file

        repo = tmp_path / "repo"
        repo.mkdir()
        reviews = repo / "reviews"
        reviews.mkdir()
        review = reviews / "mfslug_plan_review_round1.md"
        review.write_text("# Test content for hash verification\n")

        with patch("orchestrator_v3.run_recorder.discover_session_files", return_value=[]):
            recorder = RunRecorder(mode="plan", slug="mfslug", repo_root=repo)
            with recorder:
                recorder.outcome = "approved"

        sessions = repo / "maistro" / "sessions"
        archives = list(sessions.glob("*.tar.gz"))
        assert len(archives) == 1

        with _tarfile.open(archives[0], "r:gz") as tf:
            manifest_data = json.loads(tf.extractfile("manifest.json").read())

        # Find the review file in manifest and verify hash
        review_entry = next(
            (f for f in manifest_data["files"] if f["path"] == "artifacts/reviews/mfslug_plan_review_round1.md"),
            None,
        )
        assert review_entry is not None
        assert review_entry["sha256"] == sha256_file(review)
        assert review_entry["size_bytes"] == review.stat().st_size

        # meta.json must be in the manifest (N1 from round 1)
        meta_entry = next(
            (f for f in manifest_data["files"] if f["path"] == "meta.json"),
            None,
        )
        assert meta_entry is not None
        assert len(meta_entry["sha256"]) == 64

    def test_meta_json_content(self, tmp_path):
        """meta.json contains git state and timestamps."""
        import tarfile as _tarfile

        from orchestrator_v3.run_recorder import RunRecorder

        repo = tmp_path / "repo"
        repo.mkdir()

        with patch("orchestrator_v3.run_recorder.discover_session_files", return_value=[]):
            recorder = RunRecorder(mode="plan", slug="metaslug", repo_root=repo)
            with recorder:
                recorder.outcome = "approved"

        sessions = repo / "maistro" / "sessions"
        archives = list(sessions.glob("*.tar.gz"))
        assert len(archives) == 1

        with _tarfile.open(archives[0], "r:gz") as tf:
            meta = json.loads(tf.extractfile("meta.json").read())

        assert meta["run_id"] == recorder.run_id
        assert meta["mode"] == "plan"
        assert meta["slug"] == "metaslug"
        assert "git_sha" in meta
        assert "git_branch" in meta
        assert "start_time" in meta
        assert "end_time" in meta

    def test_code_archive_state_is_task_state(self, tmp_path):
        """Code mode archive maps per-task state file to run/state.json."""
        import tarfile as _tarfile

        from orchestrator_v3.run_recorder import RunRecorder

        repo = tmp_path / "repo"
        repo.mkdir()
        reviews = repo / "reviews"
        reviews.mkdir()
        (reviews / "codeslug_p1_t2_state.json").write_text('{"phase":1,"task":2}\n')

        with patch("orchestrator_v3.run_recorder.discover_session_files", return_value=[]):
            recorder = RunRecorder(
                mode="code", slug="codeslug", repo_root=repo, phase=1, task=2,
            )
            with recorder:
                recorder.outcome = "approved"

        sessions = repo / "maistro" / "sessions"
        archives = list(sessions.glob("*.tar.gz"))
        assert len(archives) == 1

        with _tarfile.open(archives[0], "r:gz") as tf:
            names = tf.getnames()

        # Code mode's primary state is the per-task state, archived as run/state.json
        assert "run/state.json" in names

    def test_archive_includes_claude_transcripts(self, tmp_path):
        """Archive includes Claude session transcripts in claude/ directory."""
        import tarfile as _tarfile

        from orchestrator_v3.run_recorder import RunRecorder

        repo = tmp_path / "repo"
        repo.mkdir()
        session = tmp_path / "session.jsonl"
        session.write_text('{"type":"message"}\n')

        with patch(
            "orchestrator_v3.run_recorder.discover_session_files",
            return_value=[session],
        ):
            recorder = RunRecorder(mode="plan", slug="sess", repo_root=repo)
            with recorder:
                recorder.outcome = "approved"

        sessions = repo / "maistro" / "sessions"
        archives = list(sessions.glob("*.tar.gz"))
        assert len(archives) == 1

        with _tarfile.open(archives[0], "r:gz") as tf:
            names = tf.getnames()

        assert "claude/session.jsonl" in names


class TestExtractFindingCounts:
    """Test finding count extraction from ORCH_META in review artifacts."""

    def test_extract_from_review_file(self, tmp_path):
        from orchestrator_v3.run_recorder import extract_finding_counts

        review = tmp_path / "slug_plan_review_round1.md"
        review.write_text(
            "<!-- ORCH_META\nVERDICT: FIXES_REQUIRED\nBLOCKER: 1\n"
            "MAJOR: 2\nMINOR: 3\nDECISIONS: 0\nVERIFIED: 0\n-->\n"
        )

        results = extract_finding_counts([str(review)])
        assert len(results) == 1
        assert results[0]["verdict"] == "FIXES_REQUIRED"
        assert results[0]["blocker"] == 1
        assert results[0]["major"] == 2
        assert results[0]["minor"] == 3

    def test_skips_non_review_artifacts(self, tmp_path):
        from orchestrator_v3.run_recorder import extract_finding_counts

        code = tmp_path / "slug_code_complete_round1.md"
        code.write_text("# Code Complete\n")

        results = extract_finding_counts([str(code)])
        assert len(results) == 0

    def test_skips_missing_files(self):
        from orchestrator_v3.run_recorder import extract_finding_counts

        results = extract_finding_counts(["/nonexistent/review_round1.md"])
        assert len(results) == 0

    def test_multiple_rounds(self, tmp_path):
        from orchestrator_v3.run_recorder import extract_finding_counts

        r1 = tmp_path / "slug_plan_review_round1.md"
        r1.write_text(
            "<!-- ORCH_META\nVERDICT: FIXES_REQUIRED\nBLOCKER: 0\n"
            "MAJOR: 3\nMINOR: 1\nDECISIONS: 0\nVERIFIED: 0\n-->\n"
        )
        r2 = tmp_path / "slug_plan_review_round2.md"
        r2.write_text(
            "<!-- ORCH_META\nVERDICT: APPROVED\nBLOCKER: 0\n"
            "MAJOR: 0\nMINOR: 0\nDECISIONS: 0\nVERIFIED: 3\n-->\n"
        )

        results = extract_finding_counts([str(r1), str(r2)])
        assert len(results) == 2
        assert results[0]["verdict"] == "FIXES_REQUIRED"
        assert results[1]["verdict"] == "APPROVED"


class TestCLIIntegration:
    """Test RunRecorder integration in CLI commands."""

    def test_plan_help_still_works(self):
        """plan --help should not be broken by RunRecorder integration."""
        from typer.testing import CliRunner

        from orchestrator_v3.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "plan" in result.output

    def test_code_help_still_works(self):
        """code --help should not be broken by RunRecorder integration."""
        from typer.testing import CliRunner

        from orchestrator_v3.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["code", "--help"])
        assert result.exit_code == 0

    def test_research_help_still_works(self):
        """research --help should not be broken by RunRecorder integration."""
        from typer.testing import CliRunner

        from orchestrator_v3.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["research", "--help"])
        assert result.exit_code == 0

    def test_run_recorder_imported_in_plan(self):
        """Verify RunRecorder is importable from run_recorder module."""
        from orchestrator_v3.run_recorder import RunRecorder

        assert RunRecorder is not None

    def test_run_recorder_used_in_plan_source(self):
        """Verify plan command source contains RunRecorder integration."""
        import inspect

        from orchestrator_v3 import cli

        source = inspect.getsource(cli.plan)
        assert "RunRecorder" in source
        assert 'mode="plan"' in source

    def test_run_recorder_used_in_code_source(self):
        """Verify code command source contains RunRecorder integration."""
        import inspect

        from orchestrator_v3 import cli

        source = inspect.getsource(cli.code)
        assert "RunRecorder" in source
        assert 'mode="code"' in source

    def test_run_recorder_used_in_research_source(self):
        """Verify research command source contains RunRecorder integration."""
        import inspect

        from orchestrator_v3 import cli

        source = inspect.getsource(cli.research)
        assert "RunRecorder" in source
        assert 'mode="research"' in source


class TestMockReviewerIntegration:
    """Integration tests verifying RunRecorder captures metadata in real CLI runs."""

    FIXTURES_DIR = Path(__file__).parent / "fixtures"

    @staticmethod
    def _get_app():
        from orchestrator_v3.cli import app
        return app

    @staticmethod
    def _mock_fixtures(base, round_reviews):
        d = base / "mock_fixtures"
        d.mkdir(parents=True, exist_ok=True)
        for round_num, content in round_reviews.items():
            (d / f"round{round_num}_review.md").write_text(content)
        return d

    @staticmethod
    def _simple_plan(base, slug):
        plans = base / "active_plans"
        plans.mkdir(parents=True, exist_ok=True)
        f = plans / f"{slug}.md"
        f.write_text(
            f"# {slug} Plan\n\n## Tasks\n\n### [ ] 1 Task\n  - [ ] 1.1 Sub\n"
        )
        return f

    @staticmethod
    def _code_plan(base, slug):
        """Create a complex plan structure for code mode tests."""
        plan_dir = base / "active_plans" / slug
        phases_dir = plan_dir / "phases"
        phases_dir.mkdir(parents=True)
        phase_file = phases_dir / "phase_0_test.md"
        phase_file.write_text(
            "# Phase 0\n\n## Tasks\n\n### [ ] 1 Task\n  - [ ] 1.1 Sub\n"
        )
        master = plan_dir / f"{slug}_master_plan.md"
        master.write_text(
            f"# {slug}\n\n## Phases Overview\n\n"
            "### Phase 0: Test\n`phases/phase_0_test.md`\n\n"
            "## Tasks\n\n### [ ] 1 Task\n  - [ ] 1.1 Sub\n"
        )
        return master

    def test_plan_recorder_captures_outcome_approved(self, tmp_path, monkeypatch):
        """Plan command sets recorder.outcome from state when approved."""
        from orchestrator_v3.run_recorder import RunRecorder

        slug = "rec_plan"
        plan_file = self._simple_plan(tmp_path, slug)
        (tmp_path / "reviews").mkdir()
        approved = self.FIXTURES_DIR / "mock_review_approved.md"
        fixture_dir = self._mock_fixtures(tmp_path, {1: approved.read_text()})
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        captured = {}
        original_exit = RunRecorder.__exit__

        def spy_exit(self_rec, *args):
            captured["outcome"] = self_rec.outcome
            captured["artifact_paths"] = list(self_rec.artifact_paths)
            captured["mode"] = self_rec.mode
            captured["run_id"] = self_rec.run_id
            return original_exit(self_rec, *args)

        with patch.object(RunRecorder, "__exit__", spy_exit):
            from typer.testing import CliRunner
            r = CliRunner().invoke(self._get_app(), [
                "plan", str(plan_file),
                "--mock-reviewer", str(fixture_dir),
                "--max-rounds", "5", "--init", "--skip-preflight",
            ])

        assert r.exit_code == 0, r.output
        assert captured["mode"] == "plan"
        assert captured["outcome"] == "approved"
        assert captured["run_id"] != ""
        assert len(captured["artifact_paths"]) > 0

    def test_plan_recorder_captures_outcome_paused(self, tmp_path, monkeypatch):
        """Plan command sets recorder.outcome to needs_response when paused."""
        from orchestrator_v3.run_recorder import RunRecorder

        slug = "rec_pause"
        plan_file = self._simple_plan(tmp_path, slug)
        (tmp_path / "reviews").mkdir()
        fixes = self.FIXTURES_DIR / "mock_review_fixes_required.md"
        fixture_dir = self._mock_fixtures(tmp_path, {1: fixes.read_text()})
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        captured = {}
        original_exit = RunRecorder.__exit__

        def spy_exit(self_rec, *args):
            captured["outcome"] = self_rec.outcome
            captured["artifact_paths"] = list(self_rec.artifact_paths)
            return original_exit(self_rec, *args)

        with patch.object(RunRecorder, "__exit__", spy_exit):
            from typer.testing import CliRunner
            r = CliRunner().invoke(self._get_app(), [
                "plan", str(plan_file),
                "--mock-reviewer", str(fixture_dir),
                "--max-rounds", "5", "--init", "--skip-preflight",
            ])

        assert r.exit_code == 0, r.output
        assert captured["outcome"] == "needs_response"

    def test_code_recorder_captures_phase_task(self, tmp_path, monkeypatch):
        """Code command passes phase/task to RunRecorder."""
        from orchestrator_v3.run_recorder import RunRecorder

        slug = "rec_code"
        self._code_plan(tmp_path, slug)
        reviews = tmp_path / "reviews"
        reviews.mkdir()
        approved = self.FIXTURES_DIR / "mock_review_approved.md"
        fixture_dir = self._mock_fixtures(tmp_path, {1: approved.read_text()})

        # Create code_complete artifact (required for code mode)
        (reviews / f"{slug}_phase_0_task_1_code_complete_round1.md").write_text(
            "# Code Complete\n\n## Files\n\nsrc/main.py\n"
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        captured = {}
        original_exit = RunRecorder.__exit__

        def spy_exit(self_rec, *args):
            captured["mode"] = self_rec.mode
            captured["phase"] = self_rec.phase
            captured["task"] = self_rec.task
            captured["outcome"] = self_rec.outcome
            captured["artifact_paths"] = list(self_rec.artifact_paths)
            return original_exit(self_rec, *args)

        with patch.object(RunRecorder, "__exit__", spy_exit):
            from typer.testing import CliRunner
            r = CliRunner().invoke(self._get_app(), [
                "code", slug, "0", "1",
                "--mock-reviewer", str(fixture_dir),
                "--max-rounds", "5", "--init", "--skip-preflight",
            ])

        assert r.exit_code == 0, r.output
        assert captured["mode"] == "code"
        assert captured["phase"] == 0
        assert captured["task"] == 1
        assert captured["outcome"] == "approved"
        assert len(captured["artifact_paths"]) > 0

    def test_research_recorder_captures_metadata(self, tmp_path, monkeypatch):
        """Research command captures mode='research', outcome, and run_id."""
        from orchestrator_v3.run_recorder import RunRecorder

        _CONVERGED_META = (
            "<!-- RESEARCH_META\nAGREEMENT: 9\nOPEN_ISSUES: 0\n"
            "DELTA: Fully aligned\n-->\n\n# Converged\nBoth agree.\n"
        )

        class _MockClaude:
            timeout = 1800
            proc = None

            def __init__(self, **_kw):
                self.responses = {
                    "intent_classification.md": "CLEAN_QUESTION",
                    "opus_initial.md": "Opus initial analysis",
                    "opus_cross_review.md": "Opus cross-review",
                    "opus_convergence_r1.md": _CONVERGED_META,
                    "synthesis.md": "# Synthesis\nFinal answer.",
                }

            def run(self, prompt, output_file, log_file):
                output_file.parent.mkdir(parents=True, exist_ok=True)
                log_file.parent.mkdir(parents=True, exist_ok=True)
                content = self.responses.get(output_file.name, "Mock response")
                output_file.write_text(content)
                log_file.write_text(f"[mock] {output_file.name}")
                return True

        class _MockCodex:
            timeout = 600
            proc = None

            def __init__(self, **_kw):
                self.responses = {
                    "codex_initial.md": "Codex initial analysis",
                    "codex_cross_review.md": "Codex cross-review",
                    "codex_convergence_r1.md": _CONVERGED_META,
                }

            def run_review(self, prompt, review_file, log_file):
                review_file.parent.mkdir(parents=True, exist_ok=True)
                log_file.parent.mkdir(parents=True, exist_ok=True)
                content = self.responses.get(review_file.name, "Mock Codex")
                review_file.write_text(content)
                log_file.write_text(f"codex\n{content}")
                return True

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        captured = {}
        original_exit = RunRecorder.__exit__

        def spy_exit(self_rec, *args):
            captured["mode"] = self_rec.mode
            captured["outcome"] = self_rec.outcome
            captured["run_id"] = self_rec.run_id
            captured["artifact_paths"] = list(self_rec.artifact_paths)
            captured["convergence_data"] = dict(self_rec.convergence_data)
            return original_exit(self_rec, *args)

        with patch.object(RunRecorder, "__exit__", spy_exit), \
             patch("orchestrator_v3.research.ClaudeRunner", _MockClaude), \
             patch("orchestrator_v3.cli.CodexReviewer", _MockCodex):
            from typer.testing import CliRunner
            r = CliRunner().invoke(self._get_app(), [
                "research", "What is testing?",
                "--slug", "rec_research",
                "--max-rounds", "5", "--skip-preflight",
            ])

        assert r.exit_code == 0, r.output
        assert captured["mode"] == "research"
        assert captured["outcome"] == "complete"
        assert captured["run_id"] != ""
        # Artifact paths must be full paths, not bare filenames
        assert len(captured["artifact_paths"]) > 0
        for ap in captured["artifact_paths"]:
            assert "rec_research" in ap, f"Expected research dir in path: {ap}"
            assert "/" in ap, f"Expected full path, got bare filename: {ap}"
        # Convergence data populated with pre-synthesis status
        assert captured["convergence_data"]["final_status"] == "converged"
        assert captured["convergence_data"]["rounds"] >= 1

    def test_research_error_sets_convergence_error(self, tmp_path, monkeypatch):
        """Research command sets convergence final_status='error' on failure."""
        from orchestrator_v3.run_recorder import RunRecorder

        class _FailClaude:
            timeout = 1800
            proc = None

            def __init__(self, **_kw):
                pass

            def run(self, prompt, output_file, log_file):
                output_file.parent.mkdir(parents=True, exist_ok=True)
                log_file.parent.mkdir(parents=True, exist_ok=True)
                # Succeed on intent classification, fail on initial analysis
                if output_file.name == "intent_classification.md":
                    output_file.write_text("CLEAN_QUESTION")
                    log_file.write_text("[mock]")
                    return True
                return False

        class _FailCodex:
            timeout = 600
            proc = None

            def __init__(self, **_kw):
                pass

            def run_review(self, prompt, review_file, log_file):
                review_file.parent.mkdir(parents=True, exist_ok=True)
                log_file.parent.mkdir(parents=True, exist_ok=True)
                return False

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_COLOR", "1")

        captured = {}
        original_exit = RunRecorder.__exit__

        def spy_exit(self_rec, *args):
            captured["outcome"] = self_rec.outcome
            captured["convergence_data"] = dict(self_rec.convergence_data)
            return original_exit(self_rec, *args)

        with patch.object(RunRecorder, "__exit__", spy_exit), \
             patch("orchestrator_v3.research.ClaudeRunner", _FailClaude), \
             patch("orchestrator_v3.cli.CodexReviewer", _FailCodex):
            from typer.testing import CliRunner
            r = CliRunner().invoke(self._get_app(), [
                "research", "Will this fail?",
                "--slug", "rec_fail",
                "--max-rounds", "5", "--skip-preflight",
            ])

        assert r.exit_code == 1
        assert captured["outcome"] == "error"
        assert captured["convergence_data"]["final_status"] == "error"
