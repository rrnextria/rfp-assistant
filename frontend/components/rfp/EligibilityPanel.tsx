"use client";

import { useMemo } from "react";
import type { EligibilityItem } from "@/lib/api";
import { StatusPill } from "./CompliancePanel";

interface Props {
  items: EligibilityItem[];
}

export function EligibilityPanel({ items }: Props) {
  const counts = useMemo(() => {
    const c = { pass: 0, fail: 0, partial: 0, unknown: 0 } as Record<string, number>;
    items.forEach((i) => {
      c[i.status] = (c[i.status] ?? 0) + 1;
    });
    return c;
  }, [items]);

  return (
    <section className="rounded-xl border bg-white p-4 shadow-sm">
      <header className="mb-2 flex items-baseline justify-between">
        <h3 className="font-semibold text-gray-900">Eligibility</h3>
        <span className="text-xs text-gray-600">
          {counts.pass} pass · {counts.fail} fail · {counts.partial} partial · {counts.unknown}{" "}
          unknown
        </span>
      </header>
      {items.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-500">No eligibility checks.</p>
      ) : (
        <ul className="divide-y">
          {items.map((i) => (
            <li key={i.id} className="flex items-start gap-3 py-2">
              <StatusPill status={i.status} />
              <div className="flex-1">
                <div className="text-sm text-gray-800">{i.label}</div>
                <div className="mt-0.5 text-xs text-gray-500">
                  <span className="uppercase tracking-wide">{i.kind}</span>
                  {i.expected != null && (
                    <>
                      {" · expected: "}
                      <span className="text-gray-700">{i.expected}</span>
                    </>
                  )}
                  {i.actual != null && (
                    <>
                      {" · actual: "}
                      <span className="text-gray-700">{i.actual}</span>
                    </>
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
