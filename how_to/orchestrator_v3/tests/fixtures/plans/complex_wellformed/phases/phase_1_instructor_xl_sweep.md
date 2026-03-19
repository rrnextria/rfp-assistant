# Phase 1: instructor_xl Saturation Sweep

**Status:** Pending
**Planned Start:** 2026-02-12
**Target End:** 2026-02-12
**Last Updated:** 2026-02-11 by Claude (Planner)
**File:** `phases/phase_1_instructor_xl_sweep.md`
**Related:** Master Plan | Prev: Phase 0 | Next: Phase 2

---

## Detailed Objective

Run the benchmark framework to discover the optimal instructor_xl configuration across GPUs 0 and 3. The sweep is adaptive: instance ceiling, batch sizes, dynamic batching, then multi-GPU combined throughput.

## Deliverables Snapshot

1. Instance ceiling data for GPUs 0 and 3.
2. Optimal batch size and dynamic batching configuration.
3. Multi-GPU combined throughput measurements and report.

## Acceptance Gates

- [ ] Gate 1: Instance ceiling discovered for GPUs 0 and 3.
- [ ] Gate 2: Optimal batch size identified.
- [ ] Gate 3: Dynamic batching impact measured.
- [ ] Gate 4: Multi-GPU burst throughput measured.
- [ ] Gate 5: Sustained load data collected.
- [ ] Gate 6: Config restored to pre-sweep state.

## Scope

- **In Scope:** Running benchmark sweeps for instructor_xl across all dimensions.
- **Out of Scope:** Modifying framework code or running bge_reranker_large sweeps.

## Interfaces & Dependencies

- Internal: Phase 0 benchmark framework (`scripts/benchmark/`).
- External: Triton Inference Server, nvidia-smi.
- Artifacts: Sweep results JSON, markdown report sections.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| OOM at low instance counts | Narrow data range | Record ceiling and focus on batch/dynamic batching |
| Thermal throttling during sustained test | Throughput degradation | Monitor temperature with 30s cooldown |

## Decision Log

- D1: Use adaptive sweep order (instances -> batch -> dynamic batching) — Status: Closed — Date: 2026-02-12

## References

### Source Files
- `scripts/benchmark/*.py` -- Phase 0 deliverables
- `models/instructor_xl/config.pbtxt`

### Destination Files
- `research/instructor_xl_sweep_results.json` -- Sweep data

### Related Documentation
- `research/gpu_saturation_report.md` -- Overall report

## Tasks

### [ ] 1 Prepare Environment and Run Single-GPU 0 Instance Scaling

  - [ ] 1.1 Verify Phase 0 prerequisites.
  - [ ] 1.2 Unload bge_reranker_large from GPU 0.
  - [ ] 1.3 Record pre-sweep MD5 of config.pbtxt.
  - [ ] 1.4 Run instance scaling sweep on GPU 0.
  - [ ] 1.5 Record instance ceiling and throughput curve.

---

### [ ] 2 Run Single-GPU 3 Instance Scaling

  - [ ] 2.1 Run instance scaling sweep on GPU 3.
  - [ ] 2.2 Record and compare to GPU 0 results.

---

### [ ] 3 Batch Size Sweep

  - [ ] 3.1 Run batch size sweep at best instance count.
  - [ ] 3.2 Record batch size vs throughput.

---

### [ ] 4 Dynamic Batching Sweep

  - [ ] 4.1 Sweep max_queue_delay_microseconds values.
  - [ ] 4.2 Use concurrent single-item requests.
  - [ ] 4.3 Record delay vs throughput and latency.

---

### [ ] 5 Multi-GPU Combined Test

  - [ ] 5.1 Deploy best config on both GPUs 0 and 3.
  - [ ] 5.2 Run burst load (500 requests).
  - [ ] 5.3 Run sustained load (60s).
  - [ ] 5.4 Compare multi-GPU to single-GPU results.
  - [ ] 5.5 Record multi-GPU throughput and scaling factor.

---

### [ ] 6 Burst vs Sustained Comparison at Best Config

  - [ ] 6.1 Run burst and sustained tests at winning config.
  - [ ] 6.2 Monitor temperature for thermal throttling.
  - [ ] 6.3 Record final results and conclusions.
  - [ ] 6.4 Generate markdown report.
  - [ ] 6.5 Verify config restored.

---

## Completion Step (Required)

After all tasks are complete, verify config restored to pre-sweep state and all results recorded.

---

## Reviewer Checklist

### Structure & Numbering

- [ ] All top-level tasks use `### [ ] N` format.
- [ ] All sub-tasks use `- [ ] N.1` format.
- [ ] No skipped numbers.
