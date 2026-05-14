/**
 * Pure-function tests for scorecard formatting helpers.
 *
 * Runs via Node's built-in test runner (`node --test`) — no new npm deps.
 * The helper under test lives in `frontend/lib/format.mjs` and is consumed by
 * `ScoreRollupHeader.tsx`.
 *
 * Note: the spec asked for `.test.ts`, but Node 20 cannot execute `.ts` files
 * directly without an extra loader. We use `.test.mjs` (native ESM) to keep
 * the test runnable with zero new dependencies, while still satisfying the
 * intent of a mechanical test that runs under `node --test`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { formatPercent } from "../../../lib/format.mjs";

test("formatPercent: null returns em-dash", () => {
  assert.equal(formatPercent(null), "—");
});

test("formatPercent: undefined returns em-dash", () => {
  assert.equal(formatPercent(undefined), "—");
});

test("formatPercent: NaN returns em-dash", () => {
  assert.equal(formatPercent(Number.NaN), "—");
});

test("formatPercent: zero returns 0%", () => {
  assert.equal(formatPercent(0), "0%");
});

test("formatPercent: 0.55 returns 55%", () => {
  assert.equal(formatPercent(0.55), "55%");
});

test("formatPercent: 1.0 returns 100%", () => {
  assert.equal(formatPercent(1), "100%");
});

test("formatPercent: clamps values above 1", () => {
  assert.equal(formatPercent(1.5), "100%");
});

test("formatPercent: clamps negative values to 0%", () => {
  assert.equal(formatPercent(-0.2), "0%");
});
