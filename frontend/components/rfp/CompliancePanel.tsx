"use client";

import { useMemo } from "react";
import type { ComplianceItem } from "@/lib/api";

interface Props {
  items: ComplianceItem[];
}

export function CompliancePanel({ items }: Props) {
  const counts = useMemo(() => {
    const c = { pass: 0, fail: 0, partial: 0, unknown: 0 };
    items.forEach((i) => {
      c[i.status] = (c[i.status] ?? 0) + 1;
    });
    return c;
  }, [items]);

  return (
    <section className="rounded-xl border bg-white p-4 shadow-sm">
      <header className="mb-2 flex items-baseline justify-between">
        <h3 className="font-semibold text-gray-900">Compliance</h3>
        <span className="text-xs text-gray-600">
          {counts.pass} pass · {counts.fail} fail · {counts.partial} partial · {counts.unknown}{" "}
          unknown
        </span>
      </header>
      {items.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-500">No compliance items.</p>
      ) : (
        <ul className="divide-y">
          {items.map((i) => (
            <li key={i.id} className="flex items-start gap-3 py-2">
              <StatusPill status={i.status} />
              <div className="flex-1">
                <div className="text-sm text-gray-800">
                  {i.label}
                  {i.mandatory && <span className="ml-1 text-rose-600" title="Mandatory">★</span>}
                </div>
                {i.evidence?.kind === "snippet" && i.evidence.excerpt && (
                  <span className="mt-1 inline-block rounded bg-violet-100 px-2 py-0.5 text-xs text-violet-800">
                    Suggested corporate response · {i.evidence.excerpt.slice(0, 60)}…
                  </span>
                )}
                {i.evidence?.kind === "citation" && i.evidence.excerpt && (
                  <span className="mt-1 inline-block rounded bg-sky-100 px-2 py-0.5 text-xs text-sky-800">
                    Citation · {i.evidence.excerpt.slice(0, 60)}…
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function StatusPill({ status }: { status: string }) {
  const cls =
    status === "pass"
      ? "bg-emerald-100 text-emerald-800"
      : status === "fail"
      ? "bg-rose-100 text-rose-800"
      : status === "partial"
      ? "bg-amber-100 text-amber-800"
      : "bg-gray-100 text-gray-700";
  return (
    <span className={`mt-0.5 rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>
  );
}
