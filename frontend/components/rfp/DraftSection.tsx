"use client";

import { useEffect, useRef, useState } from "react";
import type { RFPQuestion, RFPAnswer } from "@/lib/api";

interface Props {
  rfpId: string;
}

/**
 * Self-contained answer-drafting flow:
 *  - lists questions for the RFP,
 *  - lets the user add new ones,
 *  - generates / edits / approves AI answers,
 *  - and supports uploading a context document scoped to this RFP.
 *
 * Extracted from the previous monolithic RFPWorkspace so the workspace
 * page can render it alongside the assessment scorecard.
 */
export function DraftSection({ rfpId }: Props) {
  const [questions, setQuestions] = useState<RFPQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, RFPAnswer | null>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [generating, setGenerating] = useState<Record<string, boolean>>({});
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [approving, setApproving] = useState<Record<string, boolean>>({});
  const [newQuestion, setNewQuestion] = useState("");
  const [addingQuestion, setAddingQuestion] = useState(false);

  const [regenerating, setRegenerating] = useState(false);
  const [regenResult, setRegenResult] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Initial load: questions + each question's latest answer
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/rfps/${rfpId}/questions`, { credentials: "include" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`Failed to load questions (${r.status})`);
        return (await r.json()) as RFPQuestion[];
      })
      .then(async (qs) => {
        if (cancelled) return;
        setQuestions(qs);
        const pairs = await Promise.all(
          qs.map(async (q) => {
            try {
              const r = await fetch(
                `/api/rfps/${rfpId}/questions/${q.id}/answers/latest`,
                { credentials: "include" }
              );
              if (!r.ok) return [q.id, null] as const;
              return [q.id, (await r.json()) as RFPAnswer] as const;
            } catch {
              return [q.id, null] as const;
            }
          })
        );
        if (cancelled) return;
        setAnswers(Object.fromEntries(pairs));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Failed to load");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [rfpId]);

  async function generateAnswer(questionId: string) {
    setGenerating((p) => ({ ...p, [questionId]: true }));
    try {
      const res = await fetch(
        `/api/rfps/${rfpId}/questions/${questionId}/generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ detail_level: "balanced", user_context: {} }),
        }
      );
      if (res.ok) {
        const latestRes = await fetch(
          `/api/rfps/${rfpId}/questions/${questionId}/answers/latest`,
          { credentials: "include" }
        );
        if (latestRes.ok) {
          const saved = (await latestRes.json()) as RFPAnswer;
          setAnswers((p) => ({ ...p, [questionId]: saved }));
        }
      }
    } finally {
      setGenerating((p) => ({ ...p, [questionId]: false }));
    }
  }

  async function regenerateAll() {
    if (!confirm("Regenerate answers for all questions? This will replace existing answers."))
      return;
    setRegenerating(true);
    setRegenResult(null);
    try {
      const res = await fetch(`/api/rfps/${rfpId}/regenerate-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ detail_level: "balanced", user_context: {} }),
      });
      if (res.ok) {
        setRegenResult(
          "Regeneration started. Answers will update shortly — refresh to see results."
        );
      } else {
        setRegenResult("Failed to start regeneration. Please try again.");
      }
    } finally {
      setRegenerating(false);
    }
  }

  async function saveEdit(questionId: string, answerId: string) {
    const text = editing[questionId];
    if (text === undefined) return;
    setSaving((p) => ({ ...p, [questionId]: true }));
    try {
      const current = answers[questionId];
      const res = await fetch(
        `/api/rfps/${rfpId}/questions/${questionId}/answers/${answerId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ answer: text, version: current?.version ?? 0 }),
        }
      );
      if (res.ok) {
        const latestRes = await fetch(
          `/api/rfps/${rfpId}/questions/${questionId}/answers/latest`,
          { credentials: "include" }
        );
        if (latestRes.ok) {
          const updated = (await latestRes.json()) as RFPAnswer;
          setAnswers((p) => ({ ...p, [questionId]: updated }));
        }
        setEditing((p) => {
          const next = { ...p };
          delete next[questionId];
          return next;
        });
      }
    } finally {
      setSaving((p) => ({ ...p, [questionId]: false }));
    }
  }

  async function approveAnswer(questionId: string, answerId: string) {
    setApproving((p) => ({ ...p, [questionId]: true }));
    try {
      const res = await fetch(
        `/api/rfps/${rfpId}/questions/${questionId}/answers/${answerId}/approve`,
        { method: "POST", credentials: "include" }
      );
      if (res.ok) {
        setAnswers((p) => {
          const existing = p[questionId];
          if (!existing) return p;
          return { ...p, [questionId]: { ...existing, approved: true } };
        });
      }
    } finally {
      setApproving((p) => ({ ...p, [questionId]: false }));
    }
  }

  async function addQuestion() {
    const text = newQuestion.trim();
    if (!text) return;
    setAddingQuestion(true);
    try {
      const res = await fetch(`/api/rfps/${rfpId}/questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ questions: [text] }),
      });
      if (res.ok) {
        const data = (await res.json()) as { question_ids: string[] };
        const id = data.question_ids[0];
        const newQ: RFPQuestion = { id, rfp_id: rfpId, question: text };
        setQuestions((p) => [...p, newQ]);
        setAnswers((p) => ({ ...p, [id]: null }));
        setNewQuestion("");
      }
    } finally {
      setAddingQuestion(false);
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setUploadSuccess(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append(
        "metadata",
        JSON.stringify({
          title: file.name,
          allowed_roles: ["end_user", "content_admin", "system_admin"],
          allowed_teams: [],
          rfp_id: rfpId,
        })
      );
      const res = await fetch("/api/documents", {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        setUploadError(data.detail ?? "Upload failed");
      } else {
        setUploadSuccess(
          `"${file.name}" uploaded and being processed. Answers will be updated after processing completes.`
        );
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    } finally {
      setUploading(false);
    }
  }

  async function copyAnswer(text: string) {
    const plain = text.replace(/\[\d+\]/g, "").trim();
    await navigator.clipboard.writeText(plain);
  }

  const approvedCount = Object.values(answers).filter((a) => a?.approved).length;

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Draft answers</h2>
        <div className="flex items-center gap-2">
          <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700">
            {questions.length} question{questions.length !== 1 ? "s" : ""} · {approvedCount} approved
          </div>
          {questions.length > 0 && (
            <button
              onClick={regenerateAll}
              disabled={regenerating}
              className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 transition-colors hover:bg-indigo-100 disabled:opacity-50"
              title="Regenerate AI answers for all questions"
            >
              {regenerating ? "Starting…" : "Regenerate All"}
            </button>
          )}
        </div>
      </div>

      {regenResult && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm text-indigo-800">
          {regenResult}
        </div>
      )}

      {loadError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
          {loadError}
        </div>
      )}

      {/* Add question */}
      <div className="rounded-xl border bg-white p-4 shadow-sm">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Add RFP Question
        </p>
        <p className="mb-3 text-xs text-gray-500">
          Paste or type a question from the RFP document. Once added, click <strong>Generate Answer</strong> to have the AI draft a response.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={newQuestion}
            onChange={(e) => setNewQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addQuestion()}
            placeholder="e.g. Does the solution support AES-256 encryption at rest?"
            className="flex-1 rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
          <button
            onClick={addQuestion}
            disabled={addingQuestion || !newQuestion.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
          >
            {addingQuestion ? "Adding…" : "Add Question"}
          </button>
        </div>
      </div>

      {/* Document upload */}
      <div className="rounded-xl border bg-white p-4 shadow-sm">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Upload RFP Context Document
        </p>
        <p className="mb-3 text-xs text-gray-500">
          Upload a PDF or Word document (e.g. company profile, product spec, security whitepaper). It will be indexed and used to improve answers for this RFP.
        </p>
        <div className="flex items-center gap-3">
          <label className="flex-1">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx"
              onChange={handleFileUpload}
              disabled={uploading}
              className="block w-full text-sm text-gray-500 file:mr-3 file:rounded-lg file:border file:border-gray-300 file:bg-gray-50 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-gray-700 hover:file:bg-gray-100 disabled:opacity-50"
            />
          </label>
          {uploading && <span className="text-xs text-gray-500">Uploading…</span>}
        </div>
        {uploadError && <p className="mt-2 text-xs text-red-600">{uploadError}</p>}
        {uploadSuccess && <p className="mt-2 text-xs text-green-700">{uploadSuccess}</p>}
      </div>

      {loading ? (
        <p className="py-4 text-sm text-gray-500">Loading questions…</p>
      ) : questions.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-10 text-center">
          <p className="mb-2 text-3xl">❓</p>
          <p className="font-semibold text-gray-900">No questions yet</p>
          <p className="mt-1 text-sm text-gray-500">
            Add questions from the RFP above. The AI will generate draft answers for each one.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {questions.map((q) => {
            const answer = answers[q.id];
            const isEditing = editing[q.id] !== undefined;
            return (
              <div key={q.id} className="rounded-xl border bg-white p-4">
                <p className="mb-3 font-medium text-gray-900">{q.question}</p>
                {answer ? (
                  <div className="space-y-2">
                    {answer.approved && (
                      <span className="inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
                        Approved
                      </span>
                    )}
                    {isEditing ? (
                      <>
                        <textarea
                          rows={6}
                          value={editing[q.id]}
                          onChange={(e) =>
                            setEditing((p) => ({ ...p, [q.id]: e.target.value }))
                          }
                          className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                        <div className="flex gap-2">
                          <button
                            onClick={() => saveEdit(q.id, answer.id)}
                            disabled={saving[q.id]}
                            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                          >
                            {saving[q.id] ? "Saving…" : "Save"}
                          </button>
                          <button
                            onClick={() =>
                              setEditing((p) => {
                                const next = { ...p };
                                delete next[q.id];
                                return next;
                              })
                            }
                            className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                          >
                            Cancel
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="whitespace-pre-wrap text-sm text-foreground">
                          {answer.answer}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() =>
                              setEditing((p) => ({ ...p, [q.id]: answer.answer }))
                            }
                            className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => generateAnswer(q.id)}
                            disabled={generating[q.id]}
                            className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50"
                          >
                            {generating[q.id] ? "Regenerating…" : "Regenerate"}
                          </button>
                          <button
                            onClick={() => copyAnswer(answer.answer)}
                            className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                          >
                            Copy
                          </button>
                          {!answer.approved && (
                            <button
                              onClick={() => approveAnswer(q.id, answer.id)}
                              disabled={approving[q.id]}
                              className="rounded-md border border-green-600 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
                            >
                              {approving[q.id] ? "Approving…" : "Approve"}
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ) : (
                  <button
                    onClick={() => generateAnswer(q.id)}
                    disabled={generating[q.id]}
                    className="rounded-md bg-secondary px-3 py-1.5 text-xs font-medium hover:bg-secondary/80 disabled:opacity-50"
                  >
                    {generating[q.id] ? "Generating…" : "Generate Answer"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
