"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listContracts,
  createContract,
  type Contract,
} from "@/lib/api";

function formatValue(amount: number | null | undefined, currency: string | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${amount} ${currency ?? ""}`.trim();
  }
}

export default function ContractsPage() {
  const [items, setItems] = useState<Contract[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [clientName, setClientName] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [valueAmount, setValueAmount] = useState("");
  const [valueCurrency, setValueCurrency] = useState("USD");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    listContracts()
      .then((rows) => {
        setItems(rows);
        setError(null);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load contracts")
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !body.trim() || !clientName.trim() || !effectiveDate) return;
    setCreating(true);
    setCreateError(null);
    try {
      const amount = valueAmount.trim() ? Number(valueAmount) : undefined;
      if (amount !== undefined && Number.isNaN(amount)) {
        throw new Error("Value amount must be a number");
      }
      await createContract({
        title: title.trim(),
        body: body.trim(),
        client_name: clientName.trim(),
        effective_date: effectiveDate,
        expires_at: expiresAt || undefined,
        value_amount: amount,
        value_currency: valueCurrency.trim() || undefined,
      });
      setTitle("");
      setBody("");
      setClientName("");
      setEffectiveDate("");
      setExpiresAt("");
      setValueAmount("");
      setValueCurrency("USD");
      refresh();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create contract");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Contracts</h1>
        <p className="mt-1 text-sm text-gray-500">
          Active and historical engagements. Used as evidence for relevant-experience scoring.
        </p>
      </div>

      <form
        onSubmit={add}
        className="mb-6 space-y-3 rounded-xl border bg-white p-4 shadow-sm"
      >
        <h2 className="font-semibold text-gray-800">New contract</h2>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title (e.g. ACME 2024 MSA)"
          className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Body — contract scope / statement of work."
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
          <div className="grid grid-cols-2 gap-2">
            <input
              type="date"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              placeholder="Effective date"
              className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
            <input
              type="date"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              placeholder="Expires at (optional)"
              className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>
          <input
            type="number"
            step="0.01"
            value={valueAmount}
            onChange={(e) => setValueAmount(e.target.value)}
            placeholder="Value amount (optional)"
            className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
          <input
            value={valueCurrency}
            onChange={(e) => setValueCurrency(e.target.value)}
            placeholder="Currency (USD)"
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
            !effectiveDate
          }
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {creating ? "Adding…" : "Add contract"}
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
          <p className="font-semibold text-gray-900">No contracts yet</p>
          <p className="mt-1 text-sm text-gray-500">Add an engagement to track relevant experience.</p>
        </div>
      )}

      {items.length > 0 && (
        <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Client</th>
                <th className="px-3 py-2 text-left font-medium">Effective</th>
                <th className="px-3 py-2 text-left font-medium">Expires</th>
                <th className="px-3 py-2 text-left font-medium">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {items.map((c) => (
                <tr key={c.id}>
                  <td className="px-3 py-2 text-gray-800">{c.client_name ?? "—"}</td>
                  <td className="px-3 py-2 text-gray-700">
                    {c.effective_date ? c.effective_date.slice(0, 10) : "—"}
                  </td>
                  <td className="px-3 py-2 text-gray-700">
                    {c.expires_at ? c.expires_at.slice(0, 10) : "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-gray-800">
                    {formatValue(c.value_amount, c.value_currency)}
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
