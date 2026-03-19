"""Prompt templates for research-mode dual-model deliberation.

Each phase of the research protocol has a dedicated prompt builder method.
Intent classification determines how Phase 1 prompts are tailored.
"""

from __future__ import annotations

# ── Intent types ──────────────────────────────────────────────────────

INTENT_TYPES = (
    "CLEAN_QUESTION",
    "SEED_RESPONSE",
    "INVESTIGATION",
    "DEBUGGING",
    "GENERATIVE",
    "ADVERSARIAL",
)

_INTENT_CLASSIFICATION_PROMPT = """\
Classify the following user question into exactly ONE of these intent types:

{intent_list}

Definitions:
- CLEAN_QUESTION: A straightforward technical or conceptual question.
- SEED_RESPONSE: The user provides an existing answer and wants it validated/improved.
- INVESTIGATION: The user wants root-cause analysis or deep exploration of a topic.
- DEBUGGING: The user is troubleshooting a specific error, bug, or failure.
- GENERATIVE: The user wants new content created (design, architecture, code, prose).
- ADVERSARIAL: The user wants stress-testing, red-teaming, or devil's advocate analysis.

Respond with ONLY the intent type label, nothing else.

Question:
{question}
"""

# ── Phase 1: Initial Analysis ────────────────────────────────────────

_INITIAL_ANALYSIS_BASE = """\
You are {model_name}, participating in a structured dual-model research deliberation.

## Your Task

Provide a thorough, independent analysis of the following question. Do NOT
try to anticipate what another model might say — give YOUR best analysis.

## Question

{question}

## Intent Classification

This question has been classified as: **{intent}**
"""

_INITIAL_ANALYSIS_CLEAN = """
## Instructions

1. Break down the question into its core components.
2. Analyze each component thoroughly.
3. Provide your position with supporting evidence and reasoning.
4. Note any assumptions you are making.
5. Identify areas of uncertainty or where more information would help.
"""

_INITIAL_ANALYSIS_SEED = """
## Seed Response

The user provided the following initial response for validation:

{seed_response}

## Instructions

1. Evaluate the seed response for correctness and completeness.
2. Identify any errors, omissions, or areas that could be improved.
3. Provide your own analysis, building on or correcting the seed.
4. Note where you agree and disagree with the seed.
"""

_INITIAL_ANALYSIS_INVESTIGATION = """
## Instructions

1. Identify all relevant factors and dimensions of the question.
2. Trace causal chains and dependencies.
3. Consider historical context and precedent.
4. Provide a structured analysis with clear sections.
5. Highlight areas that need deeper investigation.
"""

_INITIAL_ANALYSIS_DEBUGGING = """
## Instructions

1. Identify the most likely root causes.
2. Propose a diagnostic approach (what to check first).
3. Consider environmental factors and edge cases.
4. Suggest specific fixes or workarounds for each hypothesis.
5. Rank hypotheses by likelihood.
"""

_INITIAL_ANALYSIS_GENERATIVE = """
## Instructions

1. Explore the design space — what are the key decisions?
2. Propose a concrete solution or design.
3. Justify your choices against alternatives.
4. Identify trade-offs and constraints.
5. Provide implementation guidance where applicable.
"""

_INITIAL_ANALYSIS_ADVERSARIAL = """
## Instructions

1. Identify the strongest form of the argument or design.
2. Find weaknesses, blind spots, and failure modes.
3. Construct specific counter-arguments or attack vectors.
4. Assess severity and likelihood of each issue found.
5. Suggest mitigations for the most critical issues.
"""

_INTENT_INSTRUCTIONS = {
    "CLEAN_QUESTION": _INITIAL_ANALYSIS_CLEAN,
    "SEED_RESPONSE": _INITIAL_ANALYSIS_SEED,
    "INVESTIGATION": _INITIAL_ANALYSIS_INVESTIGATION,
    "DEBUGGING": _INITIAL_ANALYSIS_DEBUGGING,
    "GENERATIVE": _INITIAL_ANALYSIS_GENERATIVE,
    "ADVERSARIAL": _INITIAL_ANALYSIS_ADVERSARIAL,
}

_CONTEXT_FILES_SECTION = """
## Context Files

The following files have been provided as context:

{file_list}
"""

# ── Phase 2: Cross-Review ────────────────────────────────────────────

_CROSS_REVIEW_PROMPT = """\
You are {model_name}, participating in a structured dual-model research deliberation.

## Context

You previously analyzed the following question:

{question}

Your analysis was:

---
{own_position}
---

## Cross-Review Task

{other_model_name} independently analyzed the same question and produced:

---
{other_position}
---

## Instructions

1. **Agreements**: Identify where you and {other_model_name} agree. Note shared conclusions.
2. **Disagreements**: Identify where you disagree. For each disagreement:
   - State the specific point of contention.
   - Explain why you hold your position.
   - Assess whether {other_model_name}'s argument changes your view.
3. **Enhancements**: Note insights from {other_model_name} that you missed.
4. **Revised Position**: Provide your updated analysis incorporating valid points
   from {other_model_name}. Be intellectually honest — update your view where
   the evidence warrants it, but hold firm where you have strong reasons.
"""

# ── Phase 3: Convergence ─────────────────────────────────────────────

_CONVERGENCE_PROMPT = """\
You are {model_name}, in convergence round {round_num} of a dual-model research deliberation.

## Question

{question}

## Your Latest Position

---
{own_latest}
---

## {other_model_name}'s Latest Position

---
{other_latest}
---

## Instructions

1. Focus on remaining disagreements — do NOT re-state areas of agreement.
2. For each open issue:
   - Can you converge? If so, state the agreed position.
   - If not, explain precisely why and what evidence would change your mind.
3. Update your position to reflect any new convergence.

## RESEARCH_META Block (REQUIRED)

You MUST include the following block at the TOP of your response. This is
machine-parsed — follow the format exactly.

```
<!-- RESEARCH_META
AGREEMENT: <1-10 integer — how aligned are you with {other_model_name}?>
OPEN_ISSUES: <integer — number of substantive unresolved disagreements>
DELTA: <one-line summary of what changed this round>
-->
```

- AGREEMENT 10 = fully aligned on all points
- AGREEMENT 1 = fundamental disagreement
- OPEN_ISSUES 0 = no remaining disagreements
- Be honest in your assessment — do not inflate agreement to force convergence.
"""

# ── Phase 4: Synthesis ────────────────────────────────────────────────

_SYNTHESIS_PROMPT = """\
You are synthesizing the results of a structured dual-model research deliberation.

## Original Question

{question}

## Opus Final Position

---
{opus_final}
---

## Codex Final Position

---
{codex_final}
---

## Convergence History

{convergence_summary}

## Instructions

Produce a final synthesis document with these sections:

### Agreement
Points where both models converged. State the shared conclusion clearly.

### Disagreement
Points where the models could not converge. Present both positions fairly
and explain the root cause of disagreement.

### Synthesis
Your integrated answer to the original question, weighing both perspectives.
Where models disagreed, explain which position you find stronger and why.

### Recommendations
Actionable next steps or decisions based on the synthesis.
"""


# ── Max prompt size guard ─────────────────────────────────────────────

# Codex receives prompts as CLI arguments, which have OS-level size limits.
# We cap embedded positions to avoid exceeding ~128KB total prompt size.
_MAX_POSITION_CHARS = 30_000  # ~30KB per position, ~60KB for both + overhead


def _truncate(text: str, max_chars: int = _MAX_POSITION_CHARS) -> str:
    """Truncate text to max_chars, adding a marker if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... TRUNCATED — full text available in artifact file ...]\n"


class ResearchPromptBuilder:
    """Builds prompts for each phase of the research deliberation protocol."""

    def __init__(self, question: str, intent: str, slug: str) -> None:
        self.question = question
        self.intent = intent
        self.slug = slug

    @staticmethod
    def build_intent_classification_prompt(question: str) -> str:
        """Build a prompt to classify the question's intent type."""
        intent_list = "\n".join(f"- {it}" for it in INTENT_TYPES)
        return _INTENT_CLASSIFICATION_PROMPT.format(
            intent_list=intent_list, question=question
        )

    def build_initial_analysis_prompt(
        self,
        model_name: str,
        context_files: list[str] | None = None,
        seed_response: str | None = None,
    ) -> str:
        """Build Phase 1 prompt — independent initial analysis."""
        prompt = _INITIAL_ANALYSIS_BASE.format(
            model_name=model_name,
            question=self.question,
            intent=self.intent,
        )

        instructions = _INTENT_INSTRUCTIONS.get(
            self.intent, _INITIAL_ANALYSIS_CLEAN
        )

        if self.intent == "SEED_RESPONSE" and seed_response:
            instructions = instructions.format(seed_response=seed_response)

        prompt += instructions

        if context_files:
            file_list = "\n".join(f"- `{f}`" for f in context_files)
            prompt += _CONTEXT_FILES_SECTION.format(file_list=file_list)

        return prompt

    def build_cross_review_prompt(
        self,
        model_name: str,
        own_position: str,
        other_position: str,
        other_model_name: str,
    ) -> str:
        """Build Phase 2 prompt — cross-review of the other model's analysis."""
        return _CROSS_REVIEW_PROMPT.format(
            model_name=model_name,
            question=self.question,
            own_position=_truncate(own_position),
            other_position=_truncate(other_position),
            other_model_name=other_model_name,
        )

    def build_convergence_prompt(
        self,
        model_name: str,
        own_latest: str,
        other_latest: str,
        other_model_name: str,
        round_num: int,
    ) -> str:
        """Build Phase 3 prompt — convergence iteration with RESEARCH_META."""
        return _CONVERGENCE_PROMPT.format(
            model_name=model_name,
            question=self.question,
            own_latest=_truncate(own_latest),
            other_latest=_truncate(other_latest),
            other_model_name=other_model_name,
            round_num=round_num,
        )

    def build_synthesis_prompt(
        self,
        opus_final: str,
        codex_final: str,
        convergence_history: list[dict],
    ) -> str:
        """Build Phase 4 prompt — final synthesis from both positions."""
        summary_parts = []
        for entry in convergence_history:
            model = entry.get("model", "?")
            round_num = entry.get("round", "?")
            agreement = entry.get("agreement", "?")
            issues = entry.get("open_issues", "?")
            delta = entry.get("delta", "")
            summary_parts.append(
                f"- Round {round_num} ({model}): "
                f"Agreement={agreement}, Open Issues={issues}, "
                f"Delta: {delta}"
            )
        convergence_summary = (
            "\n".join(summary_parts) if summary_parts else "No convergence rounds recorded."
        )

        return _SYNTHESIS_PROMPT.format(
            question=self.question,
            opus_final=opus_final,
            codex_final=codex_final,
            convergence_summary=convergence_summary,
        )
