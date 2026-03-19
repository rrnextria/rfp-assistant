"use client";

import { useEffect, useState } from "react";
import type { Company } from "@/lib/api";

export default function AdminCompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/companies", { credentials: "include" })
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load companies");
        return r.json() as Promise<Company[]>;
      })
      .then(setCompanies)
      .catch((e) => setFetchError(e instanceof Error ? e.message : "Error"))
      .finally(() => setLoading(false));
  }, []);

  async function createCompany() {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/companies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        setCreateError(data.detail ?? "Failed to create company");
        return;
      }
      const created = (await res.json()) as Company;
      setCompanies((prev) =>
        [...prev, { id: created.id ?? (created as { company_id?: string }).company_id ?? "", name }].sort(
          (a, b) => a.name.localeCompare(b.name)
        )
      );
      setNewName("");
    } finally {
      setCreating(false);
    }
  }

  async function deleteCompany(company: Company) {
    if (!confirm(`Remove "${company.name}" from the company list?`)) return;
    setDeleting(company.id);
    try {
      const res = await fetch(`/api/companies/${company.id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.ok || res.status === 204) {
        setCompanies((prev) => prev.filter((c) => c.id !== company.id));
      }
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Companies</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage the list of customer organizations available when creating an RFP.
          These appear as options in the Customer dropdown on the New RFP form.
        </p>
      </div>

      {/* Add company form */}
      <div className="mb-6 rounded-xl border bg-white p-5 shadow-sm">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Add Company
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="e.g. Acme Corporation"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createCompany()}
            className="flex-1 rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
          <button
            onClick={createCompany}
            disabled={creating || !newName.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {creating ? "Adding…" : "Add"}
          </button>
        </div>
        {createError && <p className="mt-2 text-sm text-red-600">{createError}</p>}
      </div>

      {loading ? (
        <p className="text-gray-500">Loading companies…</p>
      ) : fetchError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {fetchError}
        </div>
      ) : companies.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-10 text-center">
          <p className="text-3xl mb-2">🏢</p>
          <p className="font-semibold text-gray-900">No companies yet</p>
          <p className="text-sm text-gray-500 mt-1">
            Add companies above to make them available in the RFP creation form.
          </p>
        </div>
      ) : (
        <div className="overflow-auto rounded-xl border bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3 text-left">Company Name</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {companies.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{c.name}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => deleteCompany(c)}
                      disabled={deleting === c.id}
                      className="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
                    >
                      {deleting === c.id ? "…" : "Remove"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="border-t px-4 py-2 text-xs text-gray-400">
            {companies.length} compan{companies.length !== 1 ? "ies" : "y"}
          </div>
        </div>
      )}
    </div>
  );
}
