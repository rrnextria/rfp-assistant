"use client";

import type { AskMode } from "@/lib/api";

interface Props {
  mode: AskMode;
  onChange: (mode: AskMode) => void;
}

const MODES: { value: AskMode; label: string; description: string }[] = [
  { value: "answer", label: "Answer", description: "Factual answer from content" },
  { value: "draft", label: "Draft", description: "Formal RFP response draft" },
  { value: "review", label: "Review", description: "Identify gaps and improvements" },
  { value: "gap", label: "Gap", description: "List missing information" },
];

export default function ModeSelector({ mode, onChange }: Props) {
  return (
    <div
      role="tablist"
      aria-label="Answer mode"
      className="flex gap-1 rounded-lg border bg-muted/30 p-1"
    >
      {MODES.map((m) => (
        <button
          key={m.value}
          role="tab"
          aria-selected={mode === m.value}
          title={m.description}
          onClick={() => onChange(m.value)}
          className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            mode === m.value
              ? "bg-background shadow-sm text-foreground"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
