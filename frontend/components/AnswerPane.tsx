"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import type { AskMode } from "@/lib/api";

interface Props {
  text: string;
  mode: AskMode;
  streaming: boolean;
  partialCompliance?: boolean;
}

const MODE_STYLES: Record<AskMode, string> = {
  answer: "prose prose-blue max-w-none",
  draft: "prose prose-indigo max-w-none rounded-lg border-l-4 border-indigo-400 pl-4",
  review: "prose prose-amber max-w-none rounded-lg border-l-4 border-amber-400 pl-4",
  gap: "prose prose-rose max-w-none rounded-lg border-l-4 border-rose-400 pl-4",
};

const MODE_LABELS: Record<AskMode, string> = {
  answer: "Answer",
  draft: "Draft Response",
  review: "Review",
  gap: "Gap Analysis",
};

export default function AnswerPane({ text, mode, streaming, partialCompliance }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    // Strip citation refs like [1], [2] for a clean paste
    const plain = text.replace(/\[\d+\]/g, "").replace(/\n{3,}/g, "\n\n").trim();
    await navigator.clipboard.writeText(plain);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-xl border bg-card p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {MODE_LABELS[mode]}
          </span>
          {streaming && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
              Streaming…
            </span>
          )}
        </div>
        {text && !streaming && (
          <button
            onClick={handleCopy}
            className="rounded-md border px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
            title="Copy answer without citations"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        )}
      </div>

      {partialCompliance && (
        <div
          role="alert"
          className="mb-4 rounded-md bg-amber-50 border border-amber-300 px-4 py-2 text-sm text-amber-800"
        >
          <strong>Partial compliance disclosure:</strong> This answer is based on
          partially matching content. Review carefully before use.
        </div>
      )}

      <div className={MODE_STYLES[mode]}>
        <ReactMarkdown>{text}</ReactMarkdown>
      </div>
    </div>
  );
}
