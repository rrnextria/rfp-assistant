# Phase 3: Apply Best Configs and Final Report

**Status:** Pending
**Planned Start:** 2026-02-12
**Target End:** 2026-02-12
**Last Updated:** 2026-02-12 by Claude (Planner)
**File:** `phases/phase_3_apply_best_configs.md`
**Related:** Master Plan | Prev: Phase 2 | Next: None

---

## Detailed Objective

Apply the winning configurations from Phases 1 and 2 permanently to config.pbtxt files, validate both models serve correctly, and generate the final comprehensive report.

## Deliverables Snapshot

1. Updated config.pbtxt files for both models.
2. Validation benchmark confirming production readiness.
3. Comprehensive final report in markdown and JSON.

## Acceptance Gates

- [ ] Gate 1: instructor_xl config.pbtxt matches best_config values.
- [ ] Gate 2: bge_reranker_large config.pbtxt matches best_config values.
- [ ] Gate 3: Both models are loaded and ready simultaneously.
- [ ] Gate 4: Throughput within 10% of peak for both models.
- [ ] Gate 5: JSON contains experiments for both models and a summary.
- [ ] Gate 6: Report contains both model names and tabular data.

## Scope

- **In Scope:** Applying winning configs, validation benchmarks, and final report.
- **Out of Scope:** Additional sweeps or modifying model code.

## Interfaces & Dependencies

- Internal: Phases 0-2 deliverables (benchmark framework and sweep data).
- External: Triton Inference Server.
- Artifacts: Final config.pbtxt files, JSON results, markdown report.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Combined OOM with both models loaded | Cannot achieve optimal for both | Reduce bge_reranker_large instances first |
| Validation shows lower throughput | Disappointing results | 10% tolerance; note as finding |

## Decision Log

- D1: Allow 10% tolerance on validation throughput — Status: Closed — Date: 2026-02-12

## References

### Source Files
- `models/instructor_xl/config.pbtxt`
- `models/bge_reranker_large/config.pbtxt`
- `scripts/benchmark/*.py` -- Phase 0 deliverables

### Destination Files
- `research/gpu_saturation_results.json` -- Final results
- `research/gpu_saturation_report.md` -- Final report

### Related Documentation
- Phase 1 and Phase 2 results

## Tasks

### [ ] 1 Apply Winning Configurations

  - [ ] 1.1 Verify prerequisites and best_config entries.
  - [ ] 1.2 Write and reload winning instructor_xl config.
  - [ ] 1.3 Write and reload winning bge_reranker_large config.
  - [ ] 1.4 Validate both models serving together.
  - [ ] 1.5 Run validation benchmark with response_cache disabled.
  - [ ] 1.6 Re-enable response_cache for instructor_xl production.

---

### [ ] 2 Generate Final Report

  - [ ] 2.1 Finalize JSON with summary object.
  - [ ] 2.2 Generate comprehensive markdown report.
  - [ ] 2.3 Add final commentary and recommendations.

---

## Completion Step (Required)

After all tasks are complete, verify both models serving and final report generated.

---

## Reviewer Checklist

### Structure & Numbering

- [ ] All top-level tasks use `### [ ] N` format.
- [ ] All sub-tasks use `- [ ] N.1` format.
- [ ] No skipped numbers.
