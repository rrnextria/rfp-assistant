# Phase 5: RFP Service — Planner Response Round 1

**Stage:** phase_5_rfp_service
**Responding to:** review_round1.md
**Verdict received:** FIXES_REQUIRED (1 major, 1 minor)

---

## Changes Made

### M1 addressed: Confidence scoring made model-agnostic with fallback

Task 5.2 updated to define a model-agnostic confidence approach:
- If model returns logprobs (Ollama may): use max softmax probability
- If logprobs unavailable (Claude, Gemini): use retrieval-based proxy = mean cosine score of top-3 retrieved chunks × answer keyword overlap ratio
- For text/numeric: confidence = mean chunk retrieval score (unchanged)
- Threshold: confidence < 0.7 → `flagged=true` (unchanged)

### N1 addressed: Quantitative threshold added to Task 6.2

Task 6.2 (adaptive disclosure) now specifies: "if mean chunk similarity score < 0.4 OR fewer than 2 chunks are retrieved" as the definition of "partially covers." This threshold is tested in Task 6.4.

---

*Planner: Claude*
