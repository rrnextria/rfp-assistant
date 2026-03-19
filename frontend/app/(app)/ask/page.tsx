"use client";

import { useState } from "react";
import ChatBox from "@/components/ChatBox";
import ModeSelector from "@/components/ModeSelector";
import AnswerPane from "@/components/AnswerPane";
import CitationsPanel from "@/components/CitationsPanel";
import type { AskMode, Citation } from "@/lib/api";

const MODE_HELP: Record<AskMode, string> = {
  answer: "Get a direct answer backed by your product knowledge base.",
  draft: "Generate a polished draft response suitable for an RFP submission.",
  review: "Review and critique an existing answer for gaps or inaccuracies.",
  gap: "Identify what information is missing or not covered in your knowledge base.",
};

const EXAMPLE_QUESTIONS = [
  "Does the solution support AES-256 encryption at rest?",
  "What certifications does the product hold?",
  "What is the availability SLA?",
  "Does the platform support SSO and MFA?",
  "Is the solution FedRAMP authorized?",
];

export default function AskPage() {
  const [mode, setMode] = useState<AskMode>("answer");
  const [streamText, setStreamText] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [partialCompliance, setPartialCompliance] = useState(false);
  const [streaming, setStreaming] = useState(false);

  function handleStreamChunk(chunk: string) {
    setStreamText((prev) => prev + chunk);
  }

  function handleComplete(finalCitations: Citation[], isPartialCompliance: boolean) {
    setCitations(finalCitations);
    setPartialCompliance(isPartialCompliance);
    setStreaming(false);
  }

  function handleStart() {
    setStreamText("");
    setCitations([]);
    setPartialCompliance(false);
    setStreaming(true);
  }

  const hasResult = streamText || streaming;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Ask AI</h1>
        <p className="mt-1 text-sm text-gray-500">
          Ask anything about your products and the AI will search the knowledge base and generate a
          citation-backed answer.
        </p>
      </div>

      {/* Mode selector + help text */}
      <div className="mb-4">
        <ModeSelector mode={mode} onChange={setMode} />
        <p className="mt-2 text-sm text-gray-500">{MODE_HELP[mode]}</p>
      </div>

      {/* Question input */}
      <ChatBox
        mode={mode}
        onStart={handleStart}
        onChunk={handleStreamChunk}
        onComplete={handleComplete}
      />

      {/* Example questions — shown only before any query */}
      {!hasResult && (
        <div className="mt-6">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Example questions
          </p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_QUESTIONS.map((q) => (
              <span
                key={q}
                className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 shadow-sm"
              >
                {q}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Answer */}
      {hasResult && (
        <div className="mt-6">
          <AnswerPane
            text={streamText}
            mode={mode}
            streaming={streaming}
            partialCompliance={partialCompliance}
          />
        </div>
      )}

      {/* Citations */}
      {citations.length > 0 && (
        <div className="mt-4">
          <CitationsPanel citations={citations} />
        </div>
      )}
    </div>
  );
}
