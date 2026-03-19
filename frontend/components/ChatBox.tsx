"use client";

import { useState, useRef, KeyboardEvent } from "react";
import { createParser } from "eventsource-parser";
import type { AskMode, Citation, AskResponse } from "@/lib/api";

interface Props {
  mode: AskMode;
  rfpId?: string;
  onStart: () => void;
  onChunk: (chunk: string) => void;
  onComplete: (citations: Citation[], partialCompliance: boolean) => void;
}

export default function ChatBox({ mode, rfpId, onStart, onChunk, onComplete }: Props) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function submit() {
    const q = question.trim();
    if (!q || loading) return;

    setError(null);
    setLoading(true);
    onStart();

    // Cancel any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/ask?stream=true", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        signal: controller.signal,
        body: JSON.stringify({
          question: q,
          mode,
          ...(rfpId ? { rfp_id: rfpId } : {}),
        }),
      });

      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(data.detail ?? `Request failed: ${res.status}`);
        setLoading(false);
        return;
      }

      const contentType = res.headers.get("content-type") ?? "";

      if (contentType.includes("text/event-stream")) {
        // SSE streaming path
        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let finalCitations: Citation[] = [];
        let isPartialCompliance = false;

        const parser = createParser((event) => {
          if (event.type !== "event") return;
          try {
            const payload = JSON.parse(event.data) as {
              type: string;
              text?: string;
              citations?: Citation[];
              partial_compliance?: boolean;
            };
            if (payload.type === "chunk" && payload.text) {
              onChunk(payload.text);
            } else if (payload.type === "done") {
              finalCitations = payload.citations ?? [];
              isPartialCompliance = payload.partial_compliance ?? false;
            }
          } catch {
            // Non-JSON event data — treat as raw text chunk
            if (event.data && event.data !== "[DONE]") {
              onChunk(event.data);
            }
          }
        });

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          parser.feed(decoder.decode(value, { stream: true }));
        }

        onComplete(finalCitations, isPartialCompliance);
      } else {
        // Non-streaming JSON fallback
        const data = (await res.json()) as AskResponse;
        onChunk(data.answer);
        onComplete(data.citations, data.partial_compliance ?? false);
      }

      setQuestion("");
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError("Request failed. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <textarea
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
          disabled={loading}
          className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
        <button
          onClick={submit}
          disabled={loading || !question.trim()}
          className="self-end rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? "…" : "Ask"}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
