"use client";

import type { RiskItem } from "@/lib/api";

interface Props {
  risks: RiskItem[];
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-rose-200 text-rose-900",
  high: "bg-rose-100 text-rose-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-emerald-100 text-emerald-800",
};

const LIKELIHOOD_COLORS: Record<string, string> = {
  high: "bg-rose-100 text-rose-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-gray-100 text-gray-700",
};

export function RiskRegister({ risks }: Props) {
  return (
    <section className="rounded-xl border bg-white p-4 shadow-sm">
      <header className="mb-2 flex items-baseline justify-between">
        <h3 className="font-semibold text-gray-900">Risk register</h3>
        <span className="text-xs text-gray-600">
          {risks.length} risk{risks.length !== 1 ? "s" : ""}
        </span>
      </header>
      {risks.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-500">No risks identified.</p>
      ) : (
        <ul className="divide-y">
          {risks.map((r) => (
            <li key={r.id} className="py-3">
              <div className="flex items-start gap-3">
                <div className="flex flex-shrink-0 gap-1">
                  <Chip label={`sev: ${r.severity}`} cls={SEVERITY_COLORS[r.severity] ?? "bg-gray-100 text-gray-700"} />
                  <Chip label={`like: ${r.likelihood}`} cls={LIKELIHOOD_COLORS[r.likelihood] ?? "bg-gray-100 text-gray-700"} />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-900">{r.title}</div>
                  {r.description && (
                    <p className="mt-0.5 text-xs text-gray-600">{r.description}</p>
                  )}
                  {r.mitigation && (
                    <p className="mt-1 text-xs text-gray-700">
                      <span className="font-medium text-gray-800">Mitigation:</span> {r.mitigation}
                    </p>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Chip({ label, cls }: { label: string; cls: string }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>
  );
}
