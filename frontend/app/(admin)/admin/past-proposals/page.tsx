"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listPastProposals,
  createPastProposal,
  patchPastProposal,
  type PastProposal,
  type ProposalOutcome,
} from "@/lib/api";

const OUTCOMES: ProposalOutcome[] = ["pending", "won", "lost", "withdrawn"];

function outcomeBadge(outcome: string): string {
  switch (outcome) {
    case "won":
      return "bg-emerald-100 text-emerald-700";
    case "lost":
      return "bg-rose-100 text-rose-700";
    case "withdrawn":
      return "bg-gray-200 text-gray-700";
    default:
      return "bg-amber-100 text-amber-700";
  }
}

export default function PastProposalsPage() {
  const [items, setItems] = useState<PastProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [clientName, setClientName] = useState("");
  const [submittedAt, setSubmittedAt] = useState("");
  const [outcome, setOutcome] = useState<ProposalOutcome>("pending");
  const [outcomeReason, setOutcomeReason] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    listPastProposals()
      .then((rows) => {
        setItems(rows);
        setError(null);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load past proposals")
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !body.trim() || !clientName.trim() || !submittedAt) return;
    setCreating(true);
    setCreateError(null);
    try {
      await createPastProposal({
        title: title.trim(),
        body: body.trim(),
        client_name: clientName.trim(),
        submitted_at: submittedAt,
        outcome,
        outcome_reason: outcomeReason.trim() || undefined,
      });
      setTitle("");
      setBody("");
      setClientName("");
      setSubmittedAt("");
      setOutcome("pending");
      setOutcomeReason("");
      refresh();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create proposal");
    } finally {
      setCreating(false);
    }
  }

  async function updateOutcome(id: string, next: string) {
    try {
      await patchPastProposal(id, { outcome: next });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update outcome");
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Past proposals</h1>
        <p className="mt-1 text-sm text-gray-500">
          Historical bids and outcomes. Won/lost data feeds the win-probability learning loop.
        </p>
      </div>

      <form
        onSubmit={add}
        className="mb-6 space-y-3 rounded-xl border bg-white p-4 shadow-sm"
      >
        <h2 className="font-semibold text-gray-800">New past proposal</h2>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title (e.g. ACME 2024 cloud migration RFP)"
          className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Body — full proposal text used for retrieval and pattern-matching."
          rows={5}
          className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <input
            value={clientName}
            onChange={(e) => setClientName(e.target.value)}
            placeholder="Client name"
            className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
          <input
            type="date"
            value={submittedAt}
            onChange={(e) => setSubmittedAt(e.target.value)}
            className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as ProposalOutcome)}
            className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          >
            {OUTCOMES.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
          <input
            value={outcomeReason}
            onChange={(e) => setOutcomeReason(e.target.value)}
            placeholder="Outcome reason (optional)"
            className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
        {createError && <p className="text-xs text-rose-600">{createError}</p>}
        <button
          type="submit"
          disabled={
            creating ||
            !title.trim() ||
            !body.trim() ||
            !clientName.trim() ||
            !submittedAt
          }
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {creating ? "Adding…" : "Add proposal"}
        </button>
      </form>

      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {error && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
          {error}
        </div>
      )}

      {!loading && items.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center">
          <p className="font-semibold text-gray-900">No past proposals yet</p>
          <p className="mt-1 text-sm text-gray-500">
            Add at least one win or loss above so the model has signal to learn from.
          </p>
        </div>
      )}

      {items.length > 0 && (
        <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Client</th>
                <th className="px-3 py-2 text-left font-medium">Submitted</th>
                <th className="px-3 py-2 text-left font-medium">Outcome</th>
                <th className="px-3 py-2 text-left font-medium w-44">Update</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {items.map((p) => (
                <tr key={p.id}>
                  <td className="px-3 py-2 text-gray-800">{p.client_name ?? "—"}</td>
                  <td className="px-3 py-2 text-gray-700">
                    {p.submitted_at ? p.submitted_at.slice(0, 10) : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${outcomeBadge(
                        p.outcome
                      )}`}
                    >
                      {p.outcome}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={p.outcome}
                      onChange={(e) => updateOutcome(p.id, e.target.value)}
                      className="rounded-md border px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300"
                    >
                      {OUTCOMES.map((o) => (
                        <option key={o} value={o}>
                          {o}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
