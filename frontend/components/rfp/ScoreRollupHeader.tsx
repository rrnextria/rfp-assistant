"use client";

import type { Verdict } from "@/lib/api";

interface Props {
  verdict: Verdict | null;
  fitScore: number | null;
  winProbability: number | null;
  onRerun: () => void;
  isStreaming: boolean;
}

export function ScoreRollupHeader({
  verdict,
  fitScore,
  winProbability,
  onRerun,
  isStreaming,
}: Props) {
  const verdictColor =
    verdict === "bid"
      ? "text-emerald-600"
      : verdict === "no_bid"
      ? "text-rose-600"
      : "text-amber-600";
  const verdictLabel = verdict ? verdict.replace("_", "-").toUpperCase() : "—";

  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border bg-white p-4 shadow-sm">
      <div>
        <div className={`text-2xl font-semibold ${verdictColor}`}>{verdictLabel}</div>
        <div className="text-xs text-gray-500">AI recommendation</div>
      </div>
      <div className="flex flex-1 justify-center gap-8">
        <Metric label="Fit score" value={fitScore} />
        <Metric label="Win probability" value={winProbability} />
      </div>
      <button
        onClick={onRerun}
        disabled={isStreaming}
        className="rounded-md px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors disabled:opacity-50"
        style={{ backgroundColor: "var(--brand-primary, #2563eb)" }}
      >
        {isStreaming ? "Running…" : "Re-run"}
      </button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | null }) {
  const pct = value == null ? "—" : `${Math.round(value * 100)}%`;
  return (
    <div className="text-center">
      <div className="font-mono text-2xl text-gray-900">{pct}</div>
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
    </div>
  );
}
