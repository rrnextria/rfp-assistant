"use client";

import ReactMarkdown from "react-markdown";

interface Props {
  markdown: string;
}

export function ExecSummaryCard({ markdown }: Props) {
  const trimmed = (markdown ?? "").trim();
  return (
    <section className="rounded-xl border bg-white p-4 shadow-sm">
      <header className="mb-2 flex items-baseline justify-between">
        <h3 className="font-semibold text-gray-900">Executive summary</h3>
      </header>
      {trimmed.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-500">
          No summary yet — re-run the assessment to generate one.
        </p>
      ) : (
        <div className="prose prose-sm max-w-none text-gray-800">
          <ReactMarkdown>{trimmed}</ReactMarkdown>
        </div>
      )}
    </section>
  );
}
