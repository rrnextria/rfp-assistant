"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getAssessmentLatest,
  runAssessment,
  type AssessmentLatest,
} from "@/lib/api";
import { useAssessmentStream } from "@/lib/useAssessmentStream";
import { ScoreRollupHeader } from "./ScoreRollupHeader";
import { CompliancePanel } from "./CompliancePanel";
import { EligibilityPanel } from "./EligibilityPanel";
import { BestFitMatrix } from "./BestFitMatrix";
import { RiskRegister } from "./RiskRegister";
import { ExecSummaryCard } from "./ExecSummaryCard";
import { AssessmentHistoryMenu } from "./AssessmentHistoryMenu";

interface Props {
  rfpId: string;
}

export function AssessmentScorecard({ rfpId }: Props) {
  const [data, setData] = useState<AssessmentLatest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openedStream, setOpenedStream] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const stream = useAssessmentStream(rfpId, openedStream);

  // Fetch latest assessment (and refetch whenever refreshTick changes)
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAssessmentLatest(rfpId)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "load failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [rfpId, refreshTick]);

  // When stream completes, refresh the latest scorecard and close the strip.
  useEffect(() => {
    if (stream.isComplete) {
      setOpenedStream(false);
      setRefreshTick((t) => t + 1);
    }
  }, [stream.isComplete]);

  const onRerun = useCallback(async () => {
    setRunError(null);
    try {
      await runAssessment(rfpId);
      setOpenedStream(true);
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Failed to start assessment");
    }
  }, [rfpId]);

  if (loading) {
    return (
      <section className="rounded-xl border bg-white p-6 text-sm text-gray-500 shadow-sm">
        Loading assessment…
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        Failed to load assessment: {error}
      </section>
    );
  }

  const head = data?.head ?? null;

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Bid assessment</h2>
        <AssessmentHistoryMenu rfpId={rfpId} refreshKey={refreshTick} />
      </div>

      {runError && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {runError}
        </div>
      )}

      {!head && !openedStream && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
          <p className="mb-2 text-sm text-gray-700">No assessment has been run yet.</p>
          <button
            onClick={onRerun}
            className="rounded-md px-4 py-2 text-sm font-medium text-white shadow-sm"
            style={{ backgroundColor: "var(--brand-primary, #2563eb)" }}
          >
            Run assessment
          </button>
        </div>
      )}

      {openedStream && (
        <ProgressStrip stage={stream.stage} pct={stream.pct} error={stream.error} />
      )}

      {head && (
        <>
          <ScoreRollupHeader
            verdict={head.verdict}
            fitScore={head.fit_score}
            winProbability={head.win_probability}
            onRerun={onRerun}
            isStreaming={openedStream}
          />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <CompliancePanel items={data?.compliance ?? []} />
            <EligibilityPanel items={data?.eligibility ?? []} />
            <BestFitMatrix matches={data?.best_fit ?? []} />
            <RiskRegister risks={data?.risks ?? []} />
          </div>
          <ExecSummaryCard markdown={head.summary ?? ""} />
        </>
      )}
    </section>
  );
}

const STAGE_STEPS = [
  { key: "queued", label: "Queued" },
  { key: "started", label: "Parsing RFP" },
  { key: "parallel_done", label: "Compliance + Eligibility" },
  { key: "risk_done", label: "Risks + Best fit" },
  { key: "complete", label: "Summary" },
];

function ProgressStrip({
  stage,
  pct,
  error,
}: {
  stage: string;
  pct: number;
  error: string | null;
}) {
  const reached = (() => {
    const idx = STAGE_STEPS.findIndex((s) => s.key === stage);
    return idx < 0 ? 0 : idx;
  })();

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
      <div className="mb-2 flex justify-between text-xs text-blue-900">
        <span>Stage: {stage || "starting…"}</span>
        <span>{pct}%</span>
      </div>
      <div className="mb-3 h-2 overflow-hidden rounded bg-blue-100">
        <div
          className="h-2 rounded bg-blue-500 transition-all"
          style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
        />
      </div>
      <ol className="flex flex-wrap items-center justify-between gap-2 text-xs">
        {STAGE_STEPS.map((s, i) => {
          const done = i <= reached;
          return (
            <li
              key={s.key}
              className={`flex items-center gap-1 ${done ? "text-blue-900" : "text-gray-500"}`}
            >
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold ${
                  done ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-600"
                }`}
              >
                {i + 1}
              </span>
              {s.label}
            </li>
          );
        })}
      </ol>
      {error && <div className="mt-2 text-xs text-rose-600">{error}</div>}
    </div>
  );
}
