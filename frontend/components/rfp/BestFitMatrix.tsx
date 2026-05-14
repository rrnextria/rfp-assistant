"use client";

import type { BestFitMatch } from "@/lib/api";

interface Props {
  matches: BestFitMatch[];
}

export function BestFitMatrix({ matches }: Props) {
  return (
    <section className="rounded-xl border bg-white p-4 shadow-sm">
      <header className="mb-2 flex items-baseline justify-between">
        <h3 className="font-semibold text-gray-900">Best-fit matrix</h3>
        <span className="text-xs text-gray-600">
          Requirement × top-matched offering (0–100)
        </span>
      </header>
      {matches.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-500">No requirement matches yet.</p>
      ) : (
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-gray-500">
              <tr className="border-b">
                <th className="px-2 py-2 text-left font-medium">Requirement</th>
                <th className="px-2 py-2 text-left font-medium">Top offering</th>
                <th className="px-2 py-2 text-left font-medium w-48">Match</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m) => (
                <tr key={m.id} className="border-b last:border-b-0">
                  <td className="px-2 py-2 align-top text-gray-800">{m.requirement}</td>
                  <td className="px-2 py-2 align-top text-gray-700">{m.offering ?? "—"}</td>
                  <td className="px-2 py-2 align-top">
                    <MatchBar score={m.match_score} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function MatchBar({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const color =
    clamped >= 75
      ? "bg-emerald-500"
      : clamped >= 50
      ? "bg-amber-500"
      : clamped > 0
      ? "bg-rose-500"
      : "bg-gray-300";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded bg-gray-100">
        <div className={`h-2 ${color}`} style={{ width: `${clamped}%` }} />
      </div>
      <span className="w-9 text-right font-mono text-xs text-gray-700">{clamped}</span>
    </div>
  );
}
