"use client";

import { useEffect, useState } from "react";
import { listAssessments, type AssessmentHead } from "@/lib/api";

interface Props {
  rfpId: string;
  /** Bump this number to force a re-fetch (e.g. after a new assessment finishes). */
  refreshKey?: number;
}

export function AssessmentHistoryMenu({ rfpId, refreshKey = 0 }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AssessmentHead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listAssessments(rfpId)
      .then((list) => {
        if (!cancelled) setItems(list);
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
  }, [rfpId, refreshKey]);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
      >
        History {items.length > 0 && <span className="text-gray-400">· {items.length}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-72 rounded-md border bg-white py-1 shadow-lg">
          {loading && <div className="px-3 py-2 text-xs text-gray-500">Loading…</div>}
          {error && <div className="px-3 py-2 text-xs text-rose-600">{error}</div>}
          {!loading && !error && items.length === 0 && (
            <div className="px-3 py-2 text-xs text-gray-500">No prior assessments.</div>
          )}
          {!loading && !error &&
            items.map((a) => (
              <div
                key={a.id}
                className="flex items-center justify-between px-3 py-2 text-xs hover:bg-gray-50"
              >
                <div>
                  <div className="font-medium text-gray-800">v{a.version}</div>
                  <div className="text-gray-500">
                    {a.verdict ?? "—"} · {a.status}
                  </div>
                </div>
                <div className="text-right text-gray-400">
                  {a.created_at ? new Date(a.created_at).toLocaleString() : ""}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
