# Research Mode — Dual-Model Deliberation

## What It Does

Research mode automates a structured deliberation protocol between two LLMs
(Claude Opus and Codex). Each model independently analyzes a question, reviews
the other's work, and iterates toward convergence — producing a synthesized
answer that captures agreement, disagreement, and recommendations.

## When to Use

- Complex questions where a single model might have blind spots
- Validating an existing analysis against a second opinion
- Debugging sessions that benefit from multiple diagnostic perspectives
- Architecture decisions where trade-offs are subtle
- Any question where you'd manually copy-paste between two models

## The Protocol

### Phase 0: Intent Classification
A quick Claude call classifies the question into one of six intent types:
`CLEAN_QUESTION`, `SEED_RESPONSE`, `INVESTIGATION`, `DEBUGGING`,
`GENERATIVE`, or `ADVERSARIAL`. This tailors the Phase 1 prompts.

### Phase 1: Independent Analysis
Both models analyze the question independently. Neither sees the other's work.
The prompt structure varies by intent type.

### Phase 2: Cross-Review
Each model receives the other's Phase 1 analysis and produces a cross-review:
agreements, disagreements, enhancements, and a revised position.

### Phase 3: Convergence Loop
Both models iterate with access to each other's latest positions. Each response
includes a machine-readable `RESEARCH_META` block:

```
<!-- RESEARCH_META
AGREEMENT: 8
OPEN_ISSUES: 0
DELTA: Minor wording differences on retry strategy
-->
```

Convergence is reached when **both** models report `AGREEMENT >= 8` AND
`OPEN_ISSUES == 0`. The loop runs up to `--max-rounds` times.

### Phase 4: Synthesis
Opus produces a final synthesis document with sections for Agreement,
Disagreement, Synthesis, and Recommendations.

## Quick Start

```bash
# Basic usage
./how_to/maistro research "What are the tradeoffs between sync and async IO?"

# With explicit slug
./how_to/maistro research "Debug this OOM in training" --slug oom_debug

# Limit convergence rounds
./how_to/maistro research "Best approach for distributed caching?" --max-rounds 3
```

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--slug` | auto | Session identifier (auto-generated from question) |
| `--max-rounds` | 10 | Maximum convergence rounds |
| `--timeout` | 1800 | Per-model wall-clock timeout (seconds) |
| `--idle-timeout` | 600 | Kill model after N seconds of no output |
| `--claude-model` | opus | **Do not pass.** Pre-configured. Only override if user asks. |
| `--codex-model` | gpt-5.4 | **Do not pass.** Pre-configured with high reasoning. Only override if user asks. |

## Artifact Layout

```
research/<slug>/
    question.md                 # Original question
    intent_classification.md    # Phase 0 result
    opus_initial.md             # Phase 1 — Opus analysis
    codex_initial.md            # Phase 1 — Codex analysis
    opus_cross_review.md        # Phase 2 — Opus reviews Codex
    codex_cross_review.md       # Phase 2 — Codex reviews Opus
    opus_convergence_r1.md      # Phase 3 — Round 1
    codex_convergence_r1.md     # Phase 3 — Round 1
    opus_convergence_r2.md      # Phase 3 — Round 2 (if needed)
    codex_convergence_r2.md     # Phase 3 — Round 2 (if needed)
    ...
    synthesis.md                # Phase 4 — Final synthesis
    state.json                  # Session state
    logs/                       # Raw model output logs
```

## RESEARCH_META Protocol

Convergence artifacts (Phase 3) must include a machine-readable block:

```
<!-- RESEARCH_META
AGREEMENT: <1-10>
OPEN_ISSUES: <integer>
DELTA: <one-line change summary>
-->
```

- **AGREEMENT**: 1 = fundamental disagreement, 10 = fully aligned
- **OPEN_ISSUES**: Number of unresolved substantive disagreements
- **DELTA**: What changed this round
- Convergence threshold: `AGREEMENT >= 8 AND OPEN_ISSUES == 0` on both models

## Intent Types

| Intent | Description | Phase 1 Behavior |
|--------|-------------|------------------|
| CLEAN_QUESTION | Straightforward question | Standard analysis |
| SEED_RESPONSE | User provides existing answer | Validate and improve |
| INVESTIGATION | Root-cause or deep exploration | Structured investigation |
| DEBUGGING | Troubleshooting a specific issue | Hypothesis-driven diagnostics |
| GENERATIVE | Create new content/design | Design space exploration |
| ADVERSARIAL | Stress-test or red-team | Attack vector analysis |
