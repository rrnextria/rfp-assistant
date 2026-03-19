"""Research mode — dual-model deliberation engine.

Automates the 4-phase protocol where two LLMs (Claude Opus and Codex)
independently analyze a question, cross-review each other's work, iterate
toward convergence, and produce a synthesis.

Both models are called as subprocesses to avoid context bloat.
Phase 1, Phase 2, and each Phase 3 round run both models **in parallel**
using ThreadPoolExecutor to cut wall-clock time roughly in half.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from orchestrator_v3.approval import check_converged, parse_research_meta
from orchestrator_v3.config import OrchestratorSettings
from orchestrator_v3.research_prompts import INTENT_TYPES, ResearchPromptBuilder
from orchestrator_v3.reviewer import CodexReviewer

logger = logging.getLogger(__name__)


def _strip_codex_banner(text: str) -> str:
    """Strip the Codex CLI preamble from captured output.

    Codex ``exec`` output format::

        OpenAI Codex v0.111.0 (research preview)
        --------
        <key-value settings>
        --------
        user
        <echoed prompt>
        codex
        <actual response>
        tokens used
        <N>
        <response duplicate>

    We find the *last* line that is exactly ``codex`` (the assistant
    response delimiter) and return everything between it and the
    ``tokens used`` footer.  This cleanly extracts the model response
    without the banner, echoed prompt, or duplicated tail.
    """
    lines = text.split("\n")

    # Find the last 'codex' marker (assistant response delimiter)
    codex_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == "codex":
            codex_idx = i

    if codex_idx is None:
        return text  # No codex marker found, return as-is

    response_start = codex_idx + 1

    # Find 'tokens used' line to strip the footer + duplicate
    for i in range(response_start, len(lines)):
        if lines[i].strip() == "tokens used":
            return "\n".join(lines[response_start:i]).strip()

    # No 'tokens used' footer — return everything after codex marker
    return "\n".join(lines[response_start:]).strip()

# ── Stop words for slug generation ────────────────────────────────────

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "and", "but", "or", "nor", "not", "so", "yet", "both",
    "either", "neither", "each", "every", "all", "any", "few", "more",
    "most", "other", "some", "such", "no", "only", "own", "same", "than",
    "too", "very", "just", "about", "what", "which", "who", "whom",
    "this", "that", "these", "those", "i", "me", "my", "we", "our",
    "you", "your", "he", "him", "his", "she", "her", "it", "its",
    "they", "them", "their", "how", "when", "where", "why",
})


def _slugify(text: str, max_words: int = 5) -> str:
    """Generate a filesystem-safe slug from question text.

    Strips stop words, lowercases, joins with underscore, caps at 60 chars.
    """
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    filtered = [w for w in words if w not in _STOP_WORDS]
    if not filtered:
        filtered = words[:max_words] if words else ["research"]
    slug = "_".join(filtered[:max_words])
    return slug[:60]


# ── Timestamp helper ──────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Research State ────────────────────────────────────────────────────

class ResearchState(BaseModel):
    """Pydantic model representing research deliberation state."""

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    slug: str
    question: str
    intent: str = ""
    current_phase: int = 1
    convergence_round: int = 0
    max_rounds: int = 10
    status: str = "in_progress"
    opus_agreement: int | None = None
    codex_agreement: int | None = None
    open_issues: int | None = None
    started_at: str = ""
    last_updated: str = ""
    history: list[dict] = Field(default_factory=list)


class ResearchStateManager:
    """Atomic persistence for :class:`ResearchState`.

    Same tempfile + ``os.replace`` + ``.bak`` pattern as StateManager.
    """

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    def load(self) -> ResearchState:
        if not self.state_path.exists():
            raise FileNotFoundError(
                f"Research state file not found: {self.state_path}"
            )
        return ResearchState.model_validate_json(self.state_path.read_text())

    def save(self, state: ResearchState) -> ResearchState:
        os.makedirs(self.state_path.parent, exist_ok=True)
        state = state.model_copy(update={"last_updated": _now_iso()})

        if self.state_path.exists():
            shutil.copy2(self.state_path, str(self.state_path) + ".bak")

        fd = tempfile.NamedTemporaryFile(
            mode="w",
            dir=self.state_path.parent,
            suffix=".tmp",
            delete=False,
        )
        try:
            fd.write(state.model_dump_json(indent=2))
            fd.close()
            os.replace(fd.name, self.state_path)
        except BaseException:
            fd.close()
            try:
                os.unlink(fd.name)
            except OSError:
                pass
            raise
        return state

    def init(
        self,
        slug: str,
        question: str,
        max_rounds: int = 10,
    ) -> ResearchState:
        now = _now_iso()
        state = ResearchState(
            slug=slug,
            question=question,
            max_rounds=max_rounds,
            started_at=now,
            last_updated=now,
        )
        return self.save(state)

    def update(self, **kwargs) -> ResearchState:
        state = self.load()
        valid_fields = set(ResearchState.model_fields.keys())
        unknown = set(kwargs.keys()) - valid_fields
        if unknown:
            raise ValueError(
                f"Unknown research state fields: {unknown}. "
                f"Valid fields: {sorted(valid_fields)}"
            )
        new_state = state.model_copy(update=kwargs)
        validated = ResearchState.model_validate(new_state.model_dump())
        return self.save(validated)

    def record_event(
        self,
        phase: int,
        model: str,
        action: str,
        artifact: str | None = None,
        round_num: int | None = None,
        agreement: int | None = None,
        open_issues: int | None = None,
        delta: str | None = None,
    ) -> ResearchState:
        state = self.load()
        entry = {
            "phase": phase,
            "model": model,
            "action": action,
            "artifact": artifact,
            "round": round_num,
            "agreement": agreement,
            "open_issues": open_issues,
            "delta": delta,
            "timestamp": _now_iso(),
        }
        new_history = state.history + [entry]
        return self.update(history=new_history)


# ── Claude Runner ─────────────────────────────────────────────────────

class ClaudeRunner:
    """Invokes ``claude -p`` via subprocess with CLI argument prompt delivery.

    For prompts under 100 KB the prompt is passed as a positional CLI argument.
    For larger prompts it is written to a temporary file and passed via
    ``stdin=open(tmpfile)``.  Neither path pipes data through stdin.
    """

    def __init__(
        self,
        model: str | None = None,
        timeout: int = 1800,
        idle_timeout: int = 600,
    ) -> None:
        if model is None:
            from orchestrator_v3.config import _env_str
            model = _env_str("MAISTRO_CLAUDE_MODEL", "opus")
        self.model = model
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.proc: subprocess.Popen | None = None

    def run(self, prompt: str, output_file: Path, log_file: Path) -> bool:
        """Run Claude with the prompt; capture output to file.

        For prompts under 100 KB the prompt is appended as a CLI positional
        argument.  For larger prompts it is written to a temporary file and
        passed via ``stdin=open(tmpfile)``.

        Args:
            prompt: The full prompt text.
            output_file: Path to write Claude's response.
            log_file: Path for raw stdout log.

        Returns:
            True if Claude exits successfully, False on timeout or error.
        """
        cmd = [
            "claude",
            "-p",
            "--model", self.model,
            "--output-format", "text",
            "--dangerously-skip-permissions",
        ]
        log_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Strip all Claude session env vars so child claude -p doesn't
        # refuse to start when launched from inside a Claude Code session.
        env = os.environ.copy()
        for key in list(env):
            if key == "CLAUDECODE" or key.startswith(("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_")):
                del env[key]

        _PROMPT_SIZE_LIMIT = 100_000  # 100 KB
        tmp_file = None

        try:
            if len(prompt.encode("utf-8")) <= _PROMPT_SIZE_LIMIT:
                # Small prompt: pass as CLI positional argument
                cmd.append(prompt)
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
            else:
                # Large prompt: write to temp file, pass as stdin
                tmp_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False,
                )
                tmp_file.write(prompt)
                tmp_file.close()
                stdin_fh = open(tmp_file.name)
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdin=stdin_fh,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        env=env,
                        start_new_session=True,
                    )
                finally:
                    stdin_fh.close()

            self.proc = proc

            # Tee stdout to log file + capture buffer
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

            start_time = time.monotonic()
            while tee_thread.is_alive():
                tee_thread.join(timeout=5)
                elapsed = time.monotonic() - start_time
                with activity_lock:
                    idle = time.monotonic() - last_activity
                if idle > self.idle_timeout:
                    logger.warning(
                        "Claude idle for %d seconds, killing (idle_timeout=%d)",
                        int(idle), self.idle_timeout,
                    )
                    proc.kill()
                    proc.wait()
                    return False
                if elapsed > self.timeout:
                    logger.warning(
                        "Claude exceeded wall-clock timeout of %d seconds",
                        self.timeout,
                    )
                    proc.kill()
                    proc.wait()
                    return False

            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Claude process did not exit within 10s after output ended, killing"
                )
                proc.kill()
                proc.wait()
                return False

            elapsed = time.monotonic() - start_time

            if proc.returncode != 0:
                logger.warning("Claude exited with code %d", proc.returncode)
                return False

            # Empty-output detection: 0 bytes + fast exit → likely silent failure
            if len(captured) == 0 and elapsed < 30:
                logger.warning(
                    "Claude produced 0 bytes of output in %.1fs (exit code %d) "
                    "— treating as failure",
                    elapsed, proc.returncode,
                )
                return False

            # Write captured output to file
            output_file.write_bytes(bytes(captured))
            return True

        except subprocess.TimeoutExpired:
            logger.warning(
                "Claude timed out after %d seconds", self.timeout
            )
            proc.kill()
            proc.wait()
            return False
        except FileNotFoundError:
            logger.warning(
                "claude binary not found on PATH. "
                "Install with: npm install -g @anthropic-ai/claude-code"
            )
            return False
        except OSError as exc:
            logger.warning("OS error invoking claude: %s", exc)
            return False
        finally:
            self.proc = None
            if tmp_file is not None:
                try:
                    os.unlink(tmp_file.name)
                except OSError:
                    pass


# ── Research Loop ─────────────────────────────────────────────────────

class ResearchLoop:
    """Orchestrates the 4-phase dual-model research deliberation.

    Phases 1, 2, and each Phase 3 round run both models **in parallel**
    using a ThreadPoolExecutor to minimize wall-clock time.
    """

    def __init__(
        self,
        state_manager: ResearchStateManager,
        prompt_builder: ResearchPromptBuilder,
        claude_runner: ClaudeRunner,
        codex_runner: CodexReviewer,
        display,
        settings: OrchestratorSettings,
        slug: str,
    ) -> None:
        self.sm = state_manager
        self.pb = prompt_builder
        self.claude = claude_runner
        self.codex = codex_runner
        self.display = display
        self.settings = settings
        self.slug = slug
        self._research_dir = settings.research_dir / slug

    def _artifact_path(self, name: str) -> Path:
        return self._research_dir / name

    def _log_path(self, name: str) -> Path:
        return self._research_dir / "logs" / name

    def _read_artifact(self, name: str) -> str:
        path = self._artifact_path(name)
        if path.exists():
            return path.read_text()
        return ""

    def _latest_position(self, model: str, max_round: int) -> str:
        """Find the most recent position file for a model.

        Search order: convergence_rN → cross_review → initial.
        """
        prefix = "opus" if model == "opus" else "codex"
        for r in range(max_round, 0, -1):
            content = self._read_artifact(f"{prefix}_convergence_r{r}.md")
            if content:
                return content
        content = self._read_artifact(f"{prefix}_cross_review.md")
        if content:
            return content
        return self._read_artifact(f"{prefix}_initial.md")

    def _run_codex(self, prompt: str, output_file: Path, log_file: Path) -> bool:
        """Run Codex via CodexReviewer.run_review().

        CodexReviewer tees stdout to log_file but does NOT write to
        output_file (in plan/code mode, the prompt tells Codex to write
        the file itself). In research mode, we capture from the log
        and strip the Codex CLI banner (version, workdir, model, etc.).
        """
        ok = self.codex.run_review(prompt, output_file, log_file)
        if ok and log_file.exists():
            raw = log_file.read_text()
            output_file.write_text(_strip_codex_banner(raw))
        return ok

    def _run_parallel(
        self,
        opus_prompt: str,
        opus_artifact: str,
        opus_log: str,
        codex_prompt: str,
        codex_artifact: str,
        codex_log: str,
        phase: int,
        round_num: int | None = None,
    ) -> tuple[bool, bool]:
        """Run Opus and Codex in parallel. Returns (opus_ok, codex_ok)."""
        self.display.print_research_model_call("Opus + Codex (parallel)", phase, round_num)

        executor = ThreadPoolExecutor(max_workers=2)
        try:
            opus_future: Future[bool] = executor.submit(
                self.claude.run,
                opus_prompt,
                self._artifact_path(opus_artifact),
                self._log_path(opus_log),
            )
            codex_future: Future[bool] = executor.submit(
                self._run_codex,
                codex_prompt,
                self._artifact_path(codex_artifact),
                self._log_path(codex_log),
            )

            opus_ok = False
            codex_ok = False

            try:
                opus_ok = opus_future.result(timeout=self.claude.timeout + 60)
            except FutureTimeoutError:
                logger.warning("Opus future timed out, killing subprocess")
                if self.claude.proc is not None:
                    self.claude.proc.kill()

            try:
                codex_ok = codex_future.result(timeout=self.codex.timeout + 60)
            except FutureTimeoutError:
                logger.warning("Codex future timed out, killing subprocess")
                if self.codex.proc is not None:
                    self.codex.proc.kill()

            return opus_ok, codex_ok
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def run(self, max_rounds: int = 10) -> int:
        """Execute the full research protocol. Returns 0 on success, 1 on error."""
        self._research_dir.mkdir(parents=True, exist_ok=True)

        # Save the question
        question_path = self._artifact_path("question.md")
        question_path.write_text(self.pb.question)

        # ── Phase 0: Intent Classification ──
        self.display.print_research_phase(0, "Intent Classification")
        intent = self._classify_intent()
        self.pb.intent = intent
        self.sm.update(intent=intent, current_phase=0)
        self.sm.record_event(
            phase=0, model="opus", action="intent_classification",
            artifact=str(self._artifact_path("intent_classification.md")),
        )

        # ── Phase 1: Independent Analysis (PARALLEL) ──
        self.display.print_research_phase(1, "Independent Analysis")
        self.sm.update(current_phase=1)

        opus_prompt = self.pb.build_initial_analysis_prompt("Opus (Claude)")
        codex_prompt = self.pb.build_initial_analysis_prompt("Codex")

        opus_ok, codex_ok = self._run_parallel(
            opus_prompt, "opus_initial.md", "opus_initial.log",
            codex_prompt, "codex_initial.md", "codex_initial.log",
            phase=1,
        )

        self.sm.record_event(phase=1, model="opus", action="initial_analysis", artifact="opus_initial.md")
        self.sm.record_event(phase=1, model="codex", action="initial_analysis", artifact="codex_initial.md")

        if not opus_ok:
            self.display.print_research_failure(1, "Opus", "Model call failed. Check logs/opus_initial.log")
            self.sm.update(status="error")
            return 1
        if not codex_ok:
            self.display.print_research_failure(1, "Codex", "Model call failed. Check logs/codex_initial.log")
            self.sm.update(status="error")
            return 1

        # ── Phase 2: Cross-Review (PARALLEL) ──
        self.display.print_research_phase(2, "Cross-Review")
        self.sm.update(current_phase=2)

        opus_initial = self._read_artifact("opus_initial.md")
        codex_initial = self._read_artifact("codex_initial.md")

        opus_prompt = self.pb.build_cross_review_prompt(
            "Opus (Claude)", opus_initial, codex_initial, "Codex",
        )
        codex_prompt = self.pb.build_cross_review_prompt(
            "Codex", codex_initial, opus_initial, "Opus (Claude)",
        )

        opus_ok, codex_ok = self._run_parallel(
            opus_prompt, "opus_cross_review.md", "opus_cross_review.log",
            codex_prompt, "codex_cross_review.md", "codex_cross_review.log",
            phase=2,
        )

        self.sm.record_event(phase=2, model="opus", action="cross_review", artifact="opus_cross_review.md")
        self.sm.record_event(phase=2, model="codex", action="cross_review", artifact="codex_cross_review.md")

        if not opus_ok:
            self.display.print_research_failure(2, "Opus", "Model call failed. Check logs/opus_cross_review.log")
            self.sm.update(status="error")
            return 1
        if not codex_ok:
            self.display.print_research_failure(2, "Codex", "Model call failed. Check logs/codex_cross_review.log")
            self.sm.update(status="error")
            return 1

        # ── Phase 3: Convergence Loop (PARALLEL per round) ──
        self.display.print_research_phase(3, "Convergence")
        self.sm.update(current_phase=3)

        for round_num in range(1, max_rounds + 1):
            self.sm.update(convergence_round=round_num)

            opus_latest = self._latest_position("opus", round_num - 1)
            codex_latest = self._latest_position("codex", round_num - 1)

            opus_prompt = self.pb.build_convergence_prompt(
                "Opus (Claude)", opus_latest, codex_latest, "Codex", round_num,
            )
            codex_prompt = self.pb.build_convergence_prompt(
                "Codex", codex_latest, opus_latest, "Opus (Claude)", round_num,
            )

            opus_ok, codex_ok = self._run_parallel(
                opus_prompt, f"opus_convergence_r{round_num}.md", f"opus_convergence_r{round_num}.log",
                codex_prompt, f"codex_convergence_r{round_num}.md", f"codex_convergence_r{round_num}.log",
                phase=3, round_num=round_num,
            )

            if not opus_ok:
                self.display.print_research_failure(3, "Opus", f"Round {round_num} failed. Check logs/opus_convergence_r{round_num}.log")
                self.sm.update(status="error")
                return 1
            if not codex_ok:
                self.display.print_research_failure(3, "Codex", f"Round {round_num} failed. Check logs/codex_convergence_r{round_num}.log")
                self.sm.update(status="error")
                return 1

            # Check convergence
            opus_path = self._artifact_path(f"opus_convergence_r{round_num}.md")
            codex_path = self._artifact_path(f"codex_convergence_r{round_num}.md")
            opus_meta = parse_research_meta(opus_path)
            codex_meta = parse_research_meta(codex_path)

            # Warn if RESEARCH_META is missing
            if opus_meta is None:
                self.display.print_research_meta_missing("Opus", round_num)
            if codex_meta is None:
                self.display.print_research_meta_missing("Codex", round_num)

            # If BOTH models missing meta in same round, treat as error
            if opus_meta is None and codex_meta is None:
                self.display.print_research_failure(
                    3, "Both models",
                    f"Neither model produced RESEARCH_META in round {round_num}. "
                    "Cannot assess convergence. Aborting.",
                )
                self.sm.update(status="error")
                return 1

            opus_agree = opus_meta.agreement if opus_meta else None
            codex_agree = codex_meta.agreement if codex_meta else None
            issues = max(
                opus_meta.open_issues if opus_meta else 99,
                codex_meta.open_issues if codex_meta else 99,
            )
            opus_delta = opus_meta.delta if opus_meta else ""
            codex_delta = codex_meta.delta if codex_meta else ""

            self.sm.update(
                opus_agreement=opus_agree,
                codex_agreement=codex_agree,
                open_issues=issues,
            )
            self.sm.record_event(
                phase=3, model="opus", action="convergence",
                round_num=round_num, agreement=opus_agree,
                open_issues=opus_meta.open_issues if opus_meta else None,
                delta=opus_delta,
                artifact=f"opus_convergence_r{round_num}.md",
            )
            self.sm.record_event(
                phase=3, model="codex", action="convergence",
                round_num=round_num, agreement=codex_agree,
                open_issues=codex_meta.open_issues if codex_meta else None,
                delta=codex_delta,
                artifact=f"codex_convergence_r{round_num}.md",
            )

            self.display.print_research_convergence_status(
                round_num, opus_agree, codex_agree, issues,
            )

            opus_converged = check_converged(opus_path)
            codex_converged = check_converged(codex_path)

            if opus_converged and codex_converged:
                self.display.print_research_converged(round_num)
                self.sm.update(status="converged")
                break
        else:
            self.display.print_research_max_rounds(max_rounds)
            self.sm.update(status="max_rounds_reached")

        # ── Phase 4: Synthesis ──
        self.display.print_research_phase(4, "Synthesis")
        self.sm.update(current_phase=4)

        state = self.sm.load()
        opus_final = self._latest_position("opus", state.convergence_round)
        codex_final = self._latest_position("codex", state.convergence_round)

        # Build convergence history from state
        convergence_events = [
            e for e in state.history if e.get("action") == "convergence"
        ]

        prompt = self.pb.build_synthesis_prompt(
            opus_final, codex_final, convergence_events,
        )

        self.display.print_research_model_call("Opus", 4)
        synthesis_path = self._artifact_path("synthesis.md")
        ok = self.claude.run(
            prompt, synthesis_path, self._log_path("synthesis.log"),
        )
        self.sm.record_event(
            phase=4, model="opus", action="synthesis",
            artifact="synthesis.md",
        )
        if not ok:
            self.display.print_research_failure(4, "Opus", "Synthesis generation failed. Check logs/synthesis.log")
            self.sm.update(status="error")
            return 1

        self.sm.update(status="complete")
        self.display.print_research_complete(str(synthesis_path))
        return 0

    def _classify_intent(self) -> str:
        """Classify question intent via a quick Claude call."""
        prompt = ResearchPromptBuilder.build_intent_classification_prompt(
            self.pb.question,
        )
        output_file = self._artifact_path("intent_classification.md")
        log_file = self._log_path("intent_classification.log")

        ok = self.claude.run(prompt, output_file, log_file)
        if ok and output_file.exists():
            raw = output_file.read_text().strip().upper()
            # Extract first valid intent type from response
            for intent in INTENT_TYPES:
                if intent in raw:
                    return intent
        # Default fallback
        return "CLEAN_QUESTION"
