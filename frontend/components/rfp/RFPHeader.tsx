"use client";

import Link from "next/link";

interface Props {
  title: string;
  client?: string | null;
  dueDate?: string | null;
  status?: string | null;
  industry?: string | null;
  region?: string | null;
}

const STATUS_BADGE: Record<string, string> = {
  approved: "bg-green-100 text-green-700",
  in_review: "bg-yellow-100 text-yellow-700",
  draft: "bg-gray-100 text-gray-600",
};

const STATUS_LABEL: Record<string, string> = {
  approved: "Approved",
  in_review: "In Review",
  draft: "Draft",
};

export function RFPHeader({ title, client, dueDate, status, industry, region }: Props) {
  return (
    <header className="rounded-xl border bg-white p-4 shadow-sm">
      <div className="mb-1 flex items-center gap-2 text-xs text-gray-500">
        <Link href="/rfps" className="hover:text-blue-600 hover:underline">
          RFPs
        </Link>
        <span>/</span>
        <span className="truncate">{title}</span>
      </div>
      <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-600">
        {client && (
          <span>
            <span className="text-gray-500">Client:</span> {client}
          </span>
        )}
        {industry && <span>{industry}</span>}
        {region && <span>{region}</span>}
        {dueDate && (
          <span>
            <span className="text-gray-500">Due:</span> {dueDate}
          </span>
        )}
        {status && (
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              STATUS_BADGE[status] ?? "bg-gray-100 text-gray-600"
            }`}
          >
            {STATUS_LABEL[status] ?? status}
          </span>
        )}
      </div>
    </header>
  );
}
