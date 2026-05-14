"use client";

import { useEffect, useState } from "react";

export type StreamState = {
  isStreaming: boolean;
  isComplete: boolean;
  stage: string;
  pct: number;
  error: string | null;
  assessmentId: string | null;
};

const INITIAL_STATE: StreamState = {
  isStreaming: false,
  isComplete: false,
  stage: "",
  pct: 0,
  error: null,
  assessmentId: null,
};

/**
 * Subscribe to the SSE assessment stream for a single RFP.
 *
 * The stream is opened only when `opened` flips to true. The hook
 * resets its own state every time `opened` toggles to true so callers
 * can re-run an assessment by setting opened=false then true again.
 *
 * The browser hits `/api/rfps/{id}/assess?stream=true` through the
 * Next.js rewrite proxy (cookie auth) — using the same origin avoids
 * CORS pain. Set NEXT_PUBLIC_API_URL only if the gateway is on a
 * different origin in production.
 */
export function useAssessmentStream(rfpId: string, opened: boolean): StreamState {
  const [state, setState] = useState<StreamState>(INITIAL_STATE);

  useEffect(() => {
    if (!opened || !rfpId) {
      return;
    }

    // Reset state for a fresh stream
    setState({ ...INITIAL_STATE, isStreaming: true });

    // Browser: rely on the Next.js rewrite at /api/* for same-origin SSE
    // with cookie credentials. Fall back to NEXT_PUBLIC_API_URL if set.
    const base =
      typeof window !== "undefined"
        ? "/api"
        : process.env.NEXT_PUBLIC_API_URL ?? "";
    const url = `${base}/rfps/${rfpId}/assess?stream=true`;

    let es: EventSource | null = null;
    try {
      es = new EventSource(url, { withCredentials: true });
    } catch (err) {
      setState((s) => ({
        ...s,
        error: err instanceof Error ? err.message : "failed to open stream",
        isStreaming: false,
      }));
      return;
    }

    es.onmessage = (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data) as {
          event?: string;
          stage?: string;
          pct?: number;
          code?: string;
          assessment_id?: string;
        };
        if (data.event === "stage") {
          setState((s) => ({
            ...s,
            stage: data.stage ?? s.stage,
            pct: typeof data.pct === "number" ? data.pct : s.pct,
          }));
        } else if (data.event === "complete") {
          setState((s) => ({
            ...s,
            isComplete: true,
            isStreaming: false,
            pct: 100,
            assessmentId: data.assessment_id ?? s.assessmentId,
          }));
          es?.close();
        } else if (data.event === "error") {
          setState((s) => ({
            ...s,
            error: data.code ?? "stream error",
          }));
        } else if (data.event === "close") {
          es?.close();
        }
      } catch {
        // Malformed event line — ignore
      }
    };

    es.onerror = () => {
      setState((s) => ({
        ...s,
        error: s.error ?? "connection lost",
        isStreaming: false,
      }));
      es?.close();
    };

    return () => {
      es?.close();
    };
  }, [rfpId, opened]);

  return state;
}
