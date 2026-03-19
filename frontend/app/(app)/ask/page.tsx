"use client";

import { useState } from "react";
import ChatBox from "@/components/ChatBox";
import ModeSelector from "@/components/ModeSelector";
import AnswerPane from "@/components/AnswerPane";
import CitationsPanel from "@/components/CitationsPanel";
import type { AskMode, Citation } from "@/lib/api";

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

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Ask</h1>
      <ModeSelector mode={mode} onChange={setMode} />
      <div className="mt-4">
        <ChatBox
          mode={mode}
          onStart={handleStart}
          onChunk={handleStreamChunk}
          onComplete={handleComplete}
        />
      </div>
      {(streamText || streaming) && (
        <div className="mt-6">
          <AnswerPane
            text={streamText}
            mode={mode}
            streaming={streaming}
            partialCompliance={partialCompliance}
          />
        </div>
      )}
      {citations.length > 0 && (
        <div className="mt-4">
          <CitationsPanel citations={citations} />
        </div>
      )}
    </div>
  );
}
