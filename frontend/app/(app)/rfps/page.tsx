"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { RFP } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  in_review: "In Review",
  approved: "Approved",
};

const STATUS_BADGE: Record<string, string> = {
  draft: "bg-gray-100 text-gray-600",
  in_review: "bg-yellow-100 text-yellow-700",
  approved: "bg-green-100 text-green-700",
};

type SortKey = "customer" | "status" | "created_at";

const PAGE_SIZE = 10;

export default function RFPsPage() {
  const router = useRouter();
  const [rfps, setRfps] = useState<RFP[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Filters & sort
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  // Action state
  const [deleting, setDeleting] = useState<string | null>(null);
  const [updatingStatus, setUpdatingStatus] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/rfps", { credentials: "include" })
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load RFPs");
        return r.json() as Promise<RFP[]>;
      })
      .then(setRfps)
      .catch((e) => setFetchError(e instanceof Error ? e.message : "Error"))
      .finally(() => setLoading(false));
  }, []);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(1);
  }

  const filtered = useMemo(() => {
    let list = rfps;
    if (filterStatus !== "all") list = list.filter((r) => r.status === filterStatus);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (r) =>
          r.customer.toLowerCase().includes(q) ||
          r.industry.toLowerCase().includes(q) ||
          r.region.toLowerCase().includes(q)
      );
    }
    list = [...list].sort((a, b) => {
      const av = (a[sortKey] ?? "") as string;
      const bv = (b[sortKey] ?? "") as string;
      const cmp = av.localeCompare(bv);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [rfps, filterStatus, search, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  async function handleDelete(rfp: RFP) {
    if (!confirm(`Delete RFP for "${rfp.customer}"? This cannot be undone.`)) return;
    setDeleting(rfp.id);
    try {
      const res = await fetch(`/api/rfps/${rfp.id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.ok || res.status === 204) {
        setRfps((prev) => prev.filter((r) => r.id !== rfp.id));
      }
    } finally {
      setDeleting(null);
    }
  }

  async function handleStatusChange(rfp: RFP, newStatus: string) {
    setUpdatingStatus(rfp.id);
    try {
      const res = await fetch(`/api/rfps/${rfp.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        setRfps((prev) =>
          prev.map((r) => (r.id === rfp.id ? { ...r, status: newStatus } : r))
        );
      }
    } finally {
      setUpdatingStatus(null);
    }
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <span className="text-gray-300 ml-1">↕</span>;
    return <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">RFPs</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage Requests for Proposals. Click an RFP to view its questions and AI-generated answers.
          </p>
        </div>
        <Link
          href="/rfps/new"
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition-colors"
        >
          + New RFP
        </Link>
      </div>

      {fetchError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {fetchError}
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-3">
        <input
          type="search"
          placeholder="Search by customer, industry, region…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 w-72"
        />
        <select
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
          className="rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        >
          <option value="all">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="in_review">In Review</option>
          <option value="approved">Approved</option>
        </select>
        <span className="ml-auto self-center text-xs text-gray-400">
          {filtered.length} RFP{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {loading ? (
        <p className="text-gray-500 py-8 text-center">Loading…</p>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center">
          <p className="text-4xl mb-3">📋</p>
          <h3 className="text-base font-semibold text-gray-900">No RFPs found</h3>
          <p className="mt-1 text-sm text-gray-500">
            {rfps.length === 0
              ? "Create your first RFP to get started."
              : "Try adjusting your search or filters."}
          </p>
          {rfps.length === 0 && (
            <Link
              href="/rfps/new"
              className="mt-4 inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
            >
              Create RFP
            </Link>
          )}
        </div>
      ) : (
        <>
          <div className="overflow-auto rounded-xl border bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th
                    className="px-4 py-3 text-left cursor-pointer select-none hover:text-gray-700"
                    onClick={() => toggleSort("customer")}
                  >
                    Customer <SortIcon col="customer" />
                  </th>
                  <th className="px-4 py-3 text-left">Industry / Region</th>
                  <th
                    className="px-4 py-3 text-left cursor-pointer select-none hover:text-gray-700"
                    onClick={() => toggleSort("status")}
                  >
                    Status <SortIcon col="status" />
                  </th>
                  <th
                    className="px-4 py-3 text-left cursor-pointer select-none hover:text-gray-700"
                    onClick={() => toggleSort("created_at")}
                  >
                    Created <SortIcon col="created_at" />
                  </th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {paginated.map((rfp) => {
                  const status = rfp.status ?? "draft";
                  const isDeleting = deleting === rfp.id;
                  const isUpdating = updatingStatus === rfp.id;
                  return (
                    <tr key={rfp.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <Link
                          href={`/rfps/${rfp.id}`}
                          className="font-semibold text-blue-700 hover:underline"
                        >
                          {rfp.customer}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {rfp.industry}
                        {rfp.region && ` · ${rfp.region}`}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            STATUS_BADGE[status] ?? "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {STATUS_LABEL[status] ?? status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs">
                        {rfp.created_at
                          ? new Date(rfp.created_at).toLocaleDateString()
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-2">
                          <Link
                            href={`/rfps/${rfp.id}`}
                            className="rounded-md border px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                          >
                            Open
                          </Link>
                          {status !== "approved" ? (
                            <button
                              onClick={() => handleStatusChange(rfp, "approved")}
                              disabled={isUpdating}
                              className="rounded-md border border-green-500 px-2.5 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:opacity-50 transition-colors"
                            >
                              {isUpdating ? "…" : "Approve"}
                            </button>
                          ) : (
                            <button
                              onClick={() => handleStatusChange(rfp, "draft")}
                              disabled={isUpdating}
                              className="rounded-md border px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                            >
                              {isUpdating ? "…" : "Unapprove"}
                            </button>
                          )}
                          <button
                            onClick={() => handleDelete(rfp)}
                            disabled={isDeleting}
                            className="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
                          >
                            {isDeleting ? "…" : "Delete"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Pagination */}
            <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-gray-400">
              <span>
                Showing {(page - 1) * PAGE_SIZE + 1}–
                {Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
              </span>
              <div className="flex gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
                >
                  ←
                </button>
                <span className="px-2 py-1">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
                >
                  →
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
