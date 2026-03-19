# GPU Saturation Benchmark — Master Plan

---

## Executive Summary

Build a GPU saturation benchmark system that sweeps Triton instance counts, batch sizes, and dynamic batching parameters for instructor_xl (GPUs 0,3) and bge_reranker_large (GPU 0).

## Detailed Objective

The benchmark framework:
1. **Discovers GPU capacity** by incrementally adding model instances until OOM or throughput plateau
2. **Sweeps the configuration space** using an adaptive strategy
3. **Tests realistic load patterns** -- burst, sustained, and concurrent batched requests
4. **Monitors hardware** -- GPU utilization %, memory, temperature, and CPU utilization
5. **Classifies errors** -- OOM, timeout, gRPC transport errors
6. **Logs everything** -- JSON and markdown in `research/`
7. **Applies the winner** -- best-performing config.pbtxt

## Quick Navigation

| Phase | Focus | Status | File |
|---|---|---|---|
| 0 | Benchmark Framework | Pending | `phases/phase_0_benchmark_framework.md` |
| 1 | instructor_xl Saturation Sweep | Pending | `phases/phase_1_instructor_xl_sweep.md` |
| 2 | bge_reranker_large Saturation Sweep | Pending | `phases/phase_2_bge_reranker_large_sweep.md` |
| 3 | Apply Best Configs and Final Report | Pending | `phases/phase_3_apply_best_configs.md` |

## Architecture Overview

The benchmark system consists of a Python package (`scripts/benchmark/`) that interfaces with Triton Inference Server via gRPC. GPU monitoring uses nvidia-smi polling.

## Current State

Two models (instructor_xl, bge_reranker_large) are deployed on Triton with default configurations. No performance data exists.

## Desired State

Optimal configurations applied for both models with documented performance baselines.

## Global Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| OOM during sweeps | Lost progress | Graceful error handling and config restoration |
| Thermal throttling | Inconsistent data | Temperature monitoring with cooldown periods |

## Global Acceptance Gates

- [ ] Gate 1: Benchmark framework runs end-to-end for instructor_xl without manual intervention.
- [ ] Gate 2: Benchmark framework runs end-to-end for bge_reranker_large without manual intervention.
- [ ] Gate 3: `research/gpu_saturation_results.json` contains complete sweep data for both models.
- [ ] Gate 4: `research/gpu_saturation_report.md` contains methodology, results tables, and conclusions.
- [ ] Gate 5: Optimal configs applied -- both models loaded and serving requests.
- [ ] Gate 6: OOM is handled gracefully.
- [ ] Gate 7: GPU monitoring data present for every benchmark step.

## Dependency Gates

- [ ] Dependency 1: Phase 0 must complete before Phases 1-2 can begin.
- [ ] Dependency 2: Phases 1-2 must complete before Phase 3 can begin.

## Phases Overview

### Phase 0: Benchmark Framework
#### Tasks
### [ ] 1 Create Package Structure and Config Manager
  - [ ] 1.1 Create `scripts/benchmark/__init__.py`.
  - [ ] 1.2 Implement `scripts/benchmark/config_manager.py`.
### [ ] 2 Implement GPU and CPU Monitoring
  - [ ] 2.1 Implement `scripts/benchmark/gpu_monitor.py`.
### [ ] 3 Implement Text Corpus and Client Helpers
  - [ ] 3.1 Implement `scripts/benchmark/corpus.py`.
  - [ ] 3.2 Implement `scripts/benchmark/triton_client_helpers.py`.
### [ ] 4 Implement Load Generator
  - [ ] 4.1 Implement `scripts/benchmark/load_generator.py`.
### [ ] 5 Implement Experiment Logger
  - [ ] 5.1 Implement `scripts/benchmark/experiment_log.py`.
### [ ] 6 Implement Adaptive Sweep and CLI
  - [ ] 6.1 Implement `scripts/benchmark/sweep.py`.
  - [ ] 6.2 Implement `scripts/benchmark/gpu_benchmark.py`.
### [ ] 7 Integration Test the Framework
  - [ ] 7.1 Run quick mode for instructor_xl and verify output.
  - [ ] 7.2 Run dry-run sweep and verify config unchanged.
  - [ ] 7.3 Run quick mode for bge_reranker_large and verify output.
  - [ ] 7.4 Verify JSON schema and field completeness.

### Phase 1: instructor_xl Saturation Sweep
#### Tasks
### [ ] 1 Prepare Environment and Run Single-GPU 0 Instance Scaling
  - [ ] 1.1 Verify Phase 0 prerequisites.
  - [ ] 1.2 Unload bge_reranker_large from GPU 0.
  - [ ] 1.3 Record pre-sweep MD5 of config.pbtxt.
  - [ ] 1.4 Run instance scaling sweep on GPU 0.
  - [ ] 1.5 Record results and update experiment log.
### [ ] 2 Run Single-GPU 3 Instance Scaling
  - [ ] 2.1 Run instance scaling sweep on GPU 3.
  - [ ] 2.2 Record and compare results.
### [ ] 3 Batch Size Sweep
  - [ ] 3.1 Run batch size sweep at best instance count.
  - [ ] 3.2 Record batch size vs throughput results.
### [ ] 4 Dynamic Batching Sweep
  - [ ] 4.1 Sweep max_queue_delay_microseconds values.
  - [ ] 4.2 Use concurrent single-item request load pattern.
  - [ ] 4.3 Record delay vs throughput and latency results.
### [ ] 5 Multi-GPU Combined Test
  - [ ] 5.1 Deploy best config on both GPUs 0 and 3.
  - [ ] 5.2 Run burst load (500 requests).
  - [ ] 5.3 Run sustained load (60s).
  - [ ] 5.4 Compare multi-GPU vs single-GPU throughput.
  - [ ] 5.5 Record multi-GPU results.
### [ ] 6 Burst vs Sustained Comparison at Best Config
  - [ ] 6.1 Run burst and sustained tests at winning config.
  - [ ] 6.2 Monitor temperature and thermal throttling.
  - [ ] 6.3 Record final results and conclusions.
  - [ ] 6.4 Generate markdown report.
  - [ ] 6.5 Verify config restored to pre-sweep state.

### Phase 2: bge_reranker_large Saturation Sweep
#### Tasks
### [ ] 1 Baseline Benchmark and Batching Enablement
  - [ ] 1.1 Verify Phase 0 prerequisites.
  - [ ] 1.2 Unload instructor_xl from GPU 0.
  - [ ] 1.3 Record pre-sweep MD5 of config.pbtxt.
  - [ ] 1.4 Run baseline benchmark at current config.
  - [ ] 1.5 Enable and validate max_batch_size=1.
  - [ ] 1.6 Sweep batch sizes [1, 4, 8, 16, 32].
### [ ] 2 Instance Scaling on GPU 0
  - [ ] 2.1 Sweep instances from 1 to max.
  - [ ] 2.2 Record instance ceiling and throughput curve.
### [ ] 3 Dynamic Batching Sweep
  - [ ] 3.1 Sweep max_queue_delay_microseconds at best config.
  - [ ] 3.2 Record delay vs throughput results.
### [ ] 4 Sustained Load at Best Config
  - [ ] 4.1 Run 60-second sustained load at winning config.
  - [ ] 4.2 Record steady-state metrics.
  - [ ] 4.3 Write final conclusions.
  - [ ] 4.4 Generate updated markdown report.
  - [ ] 4.5 Verify config restored.

### Phase 3: Apply Best Configs and Final Report
#### Tasks
### [ ] 1 Apply Winning Configurations
  - [ ] 1.1 Verify prerequisites and best_config entries.
  - [ ] 1.2 Write and reload winning instructor_xl config.
  - [ ] 1.3 Write and reload winning bge_reranker_large config.
  - [ ] 1.4 Validate both models serving together.
  - [ ] 1.5 Run validation benchmark.
  - [ ] 1.6 Re-enable response_cache for instructor_xl.
### [ ] 2 Generate Final Report
  - [ ] 2.1 Finalize JSON with summary object.
  - [ ] 2.2 Generate comprehensive markdown report.
  - [ ] 2.3 Add final commentary and recommendations.

## Decision Log

| ID | Decision | Status |
|----|----------|--------|
| D1 | Use adaptive sweep (not Cartesian product) | Closed |
| D2 | Manipulate config.pbtxt directly | Closed |
| D3 | Disable response_cache during benchmarks | Closed |

## References

### Source Files
- `models/instructor_xl/config.pbtxt`
- `models/bge_reranker_large/config.pbtxt`

### Destination Files
- `scripts/benchmark/` -- Benchmark framework package
- `research/gpu_saturation_results.json` -- Experiment results
- `research/gpu_saturation_report.md` -- Human-readable report

### Related Documentation
- Triton Inference Server documentation

---

## Reviewer Checklist

### Structure & Numbering

- [ ] Required sections appear in the correct order.
- [ ] All mirrored tasks use correct patterns.
- [ ] No `1.1.1` items appear in the master plan.
