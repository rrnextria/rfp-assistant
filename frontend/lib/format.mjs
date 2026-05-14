/**
 * Shared formatting helpers used by scorecard / assessment components.
 *
 * Written as native ESM JavaScript so it can be imported both by the Next.js
 * TypeScript app (allowJs/bundler resolution) AND by `node --test` without a
 * compile step or any new dev dependency.
 */

/**
 * Format a 0..1 ratio as a whole-percent string ("55%"), or a dash if
 * null/undefined/NaN. Values outside [0, 1] are clamped before formatting.
 *
 * @param {number | null | undefined} n
 * @returns {string}
 */
export function formatPercent(n) {
  if (n === null || n === undefined || Number.isNaN(n)) {
    return "—";
  }
  const clamped = Math.max(0, Math.min(1, n));
  return `${Math.round(clamped * 100)}%`;
}
