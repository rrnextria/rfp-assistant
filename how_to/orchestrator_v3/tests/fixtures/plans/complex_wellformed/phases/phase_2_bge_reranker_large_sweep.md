# Phase 2: bge_reranker_large Saturation Sweep

**Status:** Pending
**Planned Start:** 2026-02-12
**Target End:** 2026-02-12
**Last Updated:** 2026-02-11 by Claude (Planner)
**File:** `phases/phase_2_bge_reranker_large_sweep.md`
**Related:** Master Plan | Prev: Phase 1 | Next: Phase 3

---

## Detailed Objective

Run the benchmark framework for bge_reranker_large on GPU 0. This model has never had batching enabled (max_batch_size=0), so enabling batching requires careful validation.

## Deliverables Snapshot

1. Batching safety determination for bge_reranker_large.
2. Instance ceiling and optimal config for GPU 0.
3. Sustained load steady-state metrics.

## Acceptance Gates

- [ ] Gate 1: Baseline benchmark at current config completed.
- [ ] Gate 2: Batching safety determined (max_batch_size > 0 tested).
- [ ] Gate 3: Instance ceiling discovered for GPU 0.
- [ ] Gate 4: Dynamic batching impact measured.
- [ ] Gate 5: Sustained load data collected (>=55s).
- [ ] Gate 6: Config restored to pre-sweep state.

## Scope

- **In Scope:** Running benchmark sweeps for bge_reranker_large and enabling batching carefully.
- **Out of Scope:** Modifying framework code or model code.

## Interfaces & Dependencies

- Internal: Phase 0 benchmark framework.
- External: Triton Inference Server, nvidia-smi.
- Artifacts: Sweep results, report sections.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Enabling batching causes shape errors | Model crashes | Test max_batch_size=1 first |
| Sequential execute() limits batching benefit | No throughput gain | Record finding and recommend code optimization |

## Decision Log

- D1: Test max_batch_size=1 before full sweep — Status: Closed — Date: 2026-02-12

## References

### Source Files
- `scripts/benchmark/*.py` -- Phase 0 deliverables
- `models/bge_reranker_large/config.pbtxt`

### Destination Files
- `research/bge_reranker_sweep_results.json` -- Sweep data

### Related Documentation
- `research/gpu_saturation_report.md` -- Overall report

## Tasks

### [ ] 1 Baseline Benchmark and Batching Enablement

  - [ ] 1.1 Verify Phase 0 prerequisites.
  - [ ] 1.2 Unload instructor_xl from GPU 0.
  - [ ] 1.3 Record pre-sweep MD5 of config.pbtxt.
  - [ ] 1.4 Run baseline benchmark at current config.
  - [ ] 1.5 Test max_batch_size=1 with correctness validation.
  - [ ] 1.6 Sweep batch sizes [1, 4, 8, 16, 32].

---

### [ ] 2 Instance Scaling on GPU 0

  - [ ] 2.1 Sweep instances from 1 to max.
  - [ ] 2.2 Record instance ceiling and throughput curve.

---

### [ ] 3 Dynamic Batching Sweep

  - [ ] 3.1 Sweep max_queue_delay_microseconds at best config.
  - [ ] 3.2 Record delay vs throughput results.

---

### [ ] 4 Sustained Load at Best Config

  - [ ] 4.1 Run 60-second sustained load at winning config.
  - [ ] 4.2 Record steady-state metrics.
  - [ ] 4.3 Write final conclusions.
  - [ ] 4.4 Generate updated markdown report.
  - [ ] 4.5 Verify config restored.

---

## Completion Step (Required)

After all tasks are complete, verify config restored and results recorded.

---

## Reviewer Checklist

### Structure & Numbering

- [ ] All top-level tasks use `### [ ] N` format.
- [ ] All sub-tasks use `- [ ] N.1` format.
- [ ] No skipped numbers.
