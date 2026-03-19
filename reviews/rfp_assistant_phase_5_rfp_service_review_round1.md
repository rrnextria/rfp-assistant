<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 0
MAJOR: 1
MINOR: 1
DECISIONS: 0
VERIFIED: 0
-->

# Phase 5: RFP Service — Plan Review Round 1

**Stage:** phase_5_rfp_service
**Round:** 1 of 5
**Verdict:** FIXES_REQUIRED

---

## Summary

Phase 5 is well-structured overall. The RFP CRUD, question management, answer versioning, and approval flow are all clearly specified. Two findings must be addressed.

---

## Findings

### M1 (Major): Confidence scoring via "max softmax probability" is model-specific and not implementable with Claude/Gemini APIs

**Location:** Task 5.2

**Finding:** Task 5.2 defines confidence for yes_no and multiple_choice as "max softmax probability of the model's answer token." This assumes access to token-level log probabilities, which:
- The Anthropic Claude API does not expose
- The Google Gemini API does not expose by default
- The Ollama API may or may not expose depending on model

Since the system explicitly supports three model adapters (Claude, Gemini, Ollama), the confidence definition must work across all three. Relying on logprobs that may be unavailable will cause the `QuestionnaireCompletionAgent` to fail silently or require model-specific code paths.

**Required fix:** Define a model-agnostic fallback confidence metric (e.g., retrieval-based proxy: mean cosine similarity of top-3 chunks × answer keyword overlap ratio) that works when logprobs are unavailable. The logprob method should be used only when the adapter indicates it is supported.

### N1 (Minor): "Partially covers" in Task 6.2 lacks a quantitative threshold

**Location:** Task 6.2

**Finding:** Task 6.2 triggers adaptive disclosure "if retrieved context only partially covers the question" but does not define what "partially" means quantitatively. Without a threshold, the implementation is arbitrary and untestable. Task 6.4's test "assert partial_compliance flag set when context coverage is below threshold" requires a threshold to be defined.

**Required fix:** Specify a concrete threshold (e.g., "if mean chunk similarity score < 0.4, or if fewer than 2 chunks are retrieved").

---

## Checklist Results

All structure/numbering checks pass. Traceability issue at Task 5.2 (logprobs not available across all adapters). Minor precision issue at Task 6.2.

---

*Reviewer: Claude*
