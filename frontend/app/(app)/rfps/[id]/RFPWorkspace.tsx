"use client";

import { useState } from "react";
import Link from "next/link";
import type { RFP, RFPQuestion, RFPAnswer } from "@/lib/api";

interface Props {
  rfp: RFP;
  questions: RFPQuestion[];
  initialAnswers: Record<string, RFPAnswer | null>;
  token: string;
}

export default function RFPWorkspace({ rfp, questions, initialAnswers, token }: Props) {
  const [answers, setAnswers] = useState<Record<string, RFPAnswer | null>>(initialAnswers);
  const [generating, setGenerating] = useState<Record<string, boolean>>({});
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [approving, setApproving] = useState<Record<string, boolean>>({});
  const [newQuestion, setNewQuestion] = useState("");
  const [addingQuestion, setAddingQuestion] = useState(false);
  const [questionsList, setQuestionsList] = useState<RFPQuestion[]>(questions);

  async function generateAnswer(questionId: string, questionText: string) {
    setGenerating((prev) => ({ ...prev, [questionId]: true }));
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          question: questionText,
          mode: "answer",
          rfp_id: rfp.id,
        }),
      });
      if (res.ok) {
        const data = (await res.json()) as { answer: string };
        // Persist the generated answer
        const patchRes = await fetch(
          `/api/rfps/${rfp.id}/questions/${questionId}/answers`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ answer: data.answer }),
          }
        );
        if (patchRes.ok) {
          const saved = (await patchRes.json()) as RFPAnswer;
          setAnswers((prev) => ({ ...prev, [questionId]: saved }));
        }
      }
    } finally {
      setGenerating((prev) => ({ ...prev, [questionId]: false }));
    }
  }

  async function saveEdit(questionId: string, answerId: string) {
    const text = editing[questionId];
    if (text === undefined) return;
    setSaving((prev) => ({ ...prev, [questionId]: true }));
    try {
      const res = await fetch(
        `/api/rfps/${rfp.id}/questions/${questionId}/answers/${answerId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ answer: text }),
        }
      );
      if (res.ok) {
        const updated = (await res.json()) as RFPAnswer;
        setAnswers((prev) => ({ ...prev, [questionId]: updated }));
        setEditing((prev) => {
          const next = { ...prev };
          delete next[questionId];
          return next;
        });
      }
    } finally {
      setSaving((prev) => ({ ...prev, [questionId]: false }));
    }
  }

  async function approveAnswer(questionId: string, answerId: string) {
    setApproving((prev) => ({ ...prev, [questionId]: true }));
    try {
      const res = await fetch(
        `/api/rfps/${rfp.id}/questions/${questionId}/answers/${answerId}/approve`,
        {
          method: "POST",
          credentials: "include",
        }
      );
      if (res.ok) {
        const updated = (await res.json()) as RFPAnswer;
        setAnswers((prev) => ({ ...prev, [questionId]: updated }));
      }
    } finally {
      setApproving((prev) => ({ ...prev, [questionId]: false }));
    }
  }

  async function addQuestion() {
    if (!newQuestion.trim()) return;
    setAddingQuestion(true);
    try {
      const res = await fetch(`/api/rfps/${rfp.id}/questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ question: newQuestion.trim() }),
      });
      if (res.ok) {
        const q = (await res.json()) as RFPQuestion;
        setQuestionsList((prev) => [...prev, q]);
        setNewQuestion("");
      }
    } finally {
      setAddingQuestion(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
        <Link href="/rfps" className="hover:underline">
          RFPs
        </Link>
        <span>/</span>
        <span>{rfp.customer}</span>
      </div>
      <h1 className="mb-1 text-2xl font-bold">{rfp.customer}</h1>
      <p className="mb-8 text-sm text-muted-foreground">
        {rfp.industry} · {rfp.region}
      </p>

      {/* Add question */}
      <div className="mb-6 flex gap-2">
        <input
          type="text"
          value={newQuestion}
          onChange={(e) => setNewQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addQuestion()}
          placeholder="Add a new question…"
          className="flex-1 rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          onClick={addQuestion}
          disabled={addingQuestion || !newQuestion.trim()}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {addingQuestion ? "Adding…" : "Add"}
        </button>
      </div>

      {questionsList.length === 0 ? (
        <p className="text-muted-foreground">No questions yet. Add one above.</p>
      ) : (
        <div className="space-y-4">
          {questionsList.map((q) => {
            const answer = answers[q.id];
            const isEditing = editing[q.id] !== undefined;
            return (
              <div key={q.id} className="rounded-xl border p-4">
                <p className="mb-3 font-medium">{q.question}</p>

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
                            setEditing((prev) => ({
                              ...prev,
                              [q.id]: e.target.value,
                            }))
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
                              setEditing((prev) => {
                                const next = { ...prev };
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
                        <div className="flex gap-2">
                          <button
                            onClick={() =>
                              setEditing((prev) => ({
                                ...prev,
                                [q.id]: answer.answer,
                              }))
                            }
                            className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                          >
                            Edit
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
                    onClick={() => generateAnswer(q.id, q.question)}
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
    </div>
  );
}
