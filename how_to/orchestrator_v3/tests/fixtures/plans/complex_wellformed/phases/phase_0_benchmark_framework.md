# Phase 0: Benchmark Framework

**Status:** Pending
**Planned Start:** 2026-02-11
**Target End:** 2026-02-12
**Last Updated:** 2026-02-11 by Claude (Planner)
**File:** `phases/phase_0_benchmark_framework.md`
**Related:** Master Plan | Prev: None | Next: Phase 1

---

## Detailed Objective

Create the complete benchmark framework in `scripts/benchmark/` -- a Python package with 9 files that can sweep Triton model configurations and measure throughput, latency, and GPU utilization.

## Deliverables Snapshot

1. Complete benchmark framework package in `scripts/benchmark/` with 9 modules.
2. CLI entry point `gpu_benchmark.py` supporting quick mode and full sweep.
3. Structured JSON and markdown logging in `research/`.

## Acceptance Gates

- [ ] Gate 1: All 9 files import without errors.
- [ ] Gate 2: ConfigManager can parse and generate config.pbtxt.
- [ ] Gate 3: GpuMonitor returns utilization data.
- [ ] Gate 4: Quick mode completes and creates JSON results.
- [ ] Gate 5: Dry-run prints sweep matrix without config changes.
- [ ] Gate 6: Error classification works correctly.

## Scope

- **In Scope:** Creating all 9 benchmark modules and integration testing.
- **Out of Scope:** Running actual sweeps (Phases 1 and 2).

## Interfaces & Dependencies

- Internal: None (new package).
- External: `tritonclient`, `nvidia-smi`, `psutil`.
- Artifacts: `scripts/benchmark/` package, JSON results, markdown reports.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Config.pbtxt parsing fragile | Corrupted config | Section-based parsing with backup |
| nvidia-smi polling overhead | Skewed measurements | 1s poll interval in background thread |

## Decision Log

- D1: Use adaptive sweep strategy — Status: Closed — Date: 2026-02-11

## References

### Source Files
- `models/instructor_xl/config.pbtxt`
- `models/bge_reranker_large/config.pbtxt`

### Destination Files
- `scripts/benchmark/__init__.py` through `scripts/benchmark/sweep.py`

### Related Documentation
- `docs/benchmark_design.md` -- Design reference

## Tasks

### [ ] 1 Create Package Structure and Config Manager

**Objective:** Create package and implement ConfigManager.

  - [ ] 1.1 Create `scripts/benchmark/__init__.py` (package marker).
  - [ ] 1.2 Implement `scripts/benchmark/config_manager.py` with parse, generate, backup, restore, apply_and_reload methods.

---

### [ ] 2 Implement GPU and CPU Monitoring

**Objective:** Background monitoring of GPU utilization, memory, temperature, and CPU.

  - [ ] 2.1 Implement `scripts/benchmark/gpu_monitor.py` with GpuMonitor class, start/stop/get_stats/reset methods.

---

### [ ] 3 Implement Text Corpus and Client Helpers

**Objective:** Text generation utilities and model-specific gRPC request builders.

  - [ ] 3.1 Implement `scripts/benchmark/corpus.py` with corpus generators and cache-busting.
  - [ ] 3.2 Implement `scripts/benchmark/triton_client_helpers.py` with request builders and response parsers.

---

### [ ] 4 Implement Load Generator

**Objective:** Three load patterns: burst, sustained, concurrent-batch.

  - [ ] 4.1 Implement `scripts/benchmark/load_generator.py` with LoadGenerator class, LoadResult dataclass, and classify_error function.

---

### [ ] 5 Implement Experiment Logger

**Objective:** Structured JSON and markdown experiment logging.

  - [ ] 5.1 Implement `scripts/benchmark/experiment_log.py` with ExperimentLog class.

---

### [ ] 6 Implement Adaptive Sweep and CLI

**Objective:** Sweep orchestration logic and CLI entry point.

  - [ ] 6.1 Implement `scripts/benchmark/sweep.py` with SweepOrchestrator.
  - [ ] 6.2 Implement `scripts/benchmark/gpu_benchmark.py` CLI with argparse.

---

### [ ] 7 Integration Test the Framework

**Objective:** Validate all modules work together end-to-end.

  - [ ] 7.1 Run quick mode for instructor_xl, verify exit code 0 and JSON output.
  - [ ] 7.2 Run dry-run sweep, verify config unchanged.
  - [ ] 7.3 Run quick mode for bge_reranker_large, verify output.
  - [ ] 7.4 Verify JSON schema completeness.

---

## Completion Step (Required)

After all tasks are complete, verify headings via grep and ensure no unexpected unchecked headings remain.

---

## Reviewer Checklist

### Structure & Numbering

- [ ] All top-level tasks use `### [ ] N` format.
- [ ] All sub-tasks use `- [ ] N.1` format.
- [ ] No numbering deeper than `1.1.1`.
- [ ] No skipped numbers.
