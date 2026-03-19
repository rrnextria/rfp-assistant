"use client";

import type { Citation } from "@/lib/api";

interface Props {
  citations: Citation[];
}

export default function CitationsPanel({ citations }: Props) {
  if (citations.length === 0) return null;

  return (
    <div className="rounded-xl border bg-muted/20 p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Citations ({citations.length})
      </h2>
      <ol className="space-y-3">
        {citations.map((c, idx) => (
          <li key={c.chunk_id} className="flex gap-3">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
              {idx + 1}
            </span>
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-muted-foreground">
                {c.doc_title || "Knowledge Base Document"}
              </p>
              <p className="mt-1 text-sm leading-relaxed text-foreground line-clamp-3">
                {c.snippet}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
