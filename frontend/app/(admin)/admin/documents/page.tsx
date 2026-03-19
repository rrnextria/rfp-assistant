"use client";

import { useEffect, useRef, useState } from "react";
import type { Document } from "@/lib/api";

type SortKey = "title" | "status" | "created_at";
type SortDir = "asc" | "desc";

const STATUS_BADGE: Record<string, string> = {
  ready: "bg-yellow-100 text-yellow-800",
  pending: "bg-gray-100 text-gray-600",
  approved: "bg-green-100 text-green-800",
  processing: "bg-blue-100 text-blue-700",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  processing: "Processing…",
  ready: "Ready for Review",
  approved: "Approved",
};

export default function AdminDocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [approving, setApproving] = useState<Record<string, boolean>>({});
  const [deleting, setDeleting] = useState<Record<string, boolean>>({});
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Upload form
  const fileRef = useRef<HTMLInputElement>(null);
  const [product, setProduct] = useState("");
  const [region, setRegion] = useState("");
  const [industry, setIndustry] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);

  function loadDocuments() {
    setLoading(true);
    fetch("/api/documents", { credentials: "include" })
      .then(async (res) => {
        if (!res.ok) throw new Error("Failed to fetch documents");
        return res.json() as Promise<Document[]>;
      })
      .then(setDocuments)
      .catch((err) => setFetchError(err instanceof Error ? err.message : "Error"))
      .finally(() => setLoading(false));
  }

  useEffect(loadDocuments, []);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const sorted = [...documents].sort((a, b) => {
    const av = (a[sortKey] as string | undefined) ?? "";
    const bv = (b[sortKey] as string | undefined) ?? "";
    return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
  });

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <span className="ml-1 text-gray-300">↕</span>;
    return <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  async function approveDocument(docId: string) {
    setApproving((p) => ({ ...p, [docId]: true }));
    try {
      const res = await fetch(`/api/documents/${docId}/approve`, {
        method: "PATCH",
        credentials: "include",
      });
      if (res.ok) {
        setDocuments((prev) =>
          prev.map((d) => (d.id === docId ? { ...d, status: "approved" } : d))
        );
      }
    } finally {
      setApproving((p) => ({ ...p, [docId]: false }));
    }
  }

  async function deleteDocument(docId: string, title: string) {
    if (!confirm(`Delete "${title}"? This will also remove all its searchable chunks.`)) return;
    setDeleting((p) => ({ ...p, [docId]: true }));
    try {
      const res = await fetch(`/api/documents/${docId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.ok || res.status === 204) {
        setDocuments((prev) => prev.filter((d) => d.id !== docId));
      }
    } finally {
      setDeleting((p) => ({ ...p, [docId]: false }));
    }
  }

  async function uploadDocument() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploadSuccess(false);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append(
        "metadata",
        JSON.stringify({
          product,
          region,
          industry,
          allowed_teams: [],
          allowed_roles: ["system_admin", "content_admin", "end_user"],
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
        return;
      }
      setUploadSuccess(true);
      setProduct("");
      setRegion("");
      setIndustry("");
      if (fileRef.current) fileRef.current.value = "";
      loadDocuments();
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Documents</h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload product and sales documents. Approved documents are indexed for AI retrieval.
        </p>
      </div>

      {/* Upload form */}
      <div className="mb-8 rounded-xl border bg-white p-5 shadow-sm">
        <h2 className="mb-3 font-semibold text-gray-800">Upload Document</h2>
        <p className="mb-3 text-xs text-gray-500">
          Supported formats: PDF, DOCX (max 50 MB). After upload the document is processed automatically.
          Once processing is complete, click <strong>Approve</strong> to make it available for AI-powered searches and RFP answers.
        </p>
        <div className="space-y-3">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx"
            className="block w-full text-sm text-gray-600 file:mr-3 file:rounded-lg file:border-0 file:bg-blue-600 file:px-4 file:py-2 file:text-xs file:font-semibold file:text-white hover:file:bg-blue-700"
          />
          <div className="grid grid-cols-3 gap-3">
            <input
              type="text"
              placeholder="Product (e.g. Cloud Storage Suite)"
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
            <input
              type="text"
              placeholder="Region (e.g. North America)"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
            <input
              type="text"
              placeholder="Industry (e.g. Financial Services)"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>
          {uploadError && <p className="text-sm text-red-600">{uploadError}</p>}
          {uploadSuccess && (
            <p className="text-sm text-green-700">
              ✓ Document uploaded and queued for processing. Refresh in a moment to see its status.
            </p>
          )}
          <button
            onClick={uploadDocument}
            disabled={uploading}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {uploading ? "Uploading…" : "Upload Document"}
          </button>
        </div>
      </div>

      {/* Document table */}
      {loading ? (
        <p className="text-gray-500">Loading documents…</p>
      ) : fetchError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {fetchError}
        </div>
      ) : sorted.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center">
          <p className="text-4xl mb-3">📄</p>
          <p className="font-semibold text-gray-900">No documents yet</p>
          <p className="text-sm text-gray-500 mt-1">Upload a PDF or DOCX above to get started.</p>
        </div>
      ) : (
        <div className="overflow-auto rounded-xl border bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th
                  className="cursor-pointer px-4 py-3 text-left hover:text-gray-700"
                  onClick={() => toggleSort("title")}
                >
                  Title <SortIcon col="title" />
                </th>
                <th
                  className="cursor-pointer px-4 py-3 text-left hover:text-gray-700"
                  onClick={() => toggleSort("status")}
                >
                  Status <SortIcon col="status" />
                </th>
                <th
                  className="cursor-pointer px-4 py-3 text-left hover:text-gray-700"
                  onClick={() => toggleSort("created_at")}
                >
                  Uploaded <SortIcon col="created_at" />
                </th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {sorted.map((doc) => (
                <tr key={doc.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900 max-w-sm truncate">
                    {doc.title}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        STATUS_BADGE[doc.status] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {STATUS_LABEL[doc.status] ?? doc.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {doc.created_at
                      ? new Date(doc.created_at).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      {doc.status !== "approved" && (
                        <button
                          onClick={() => approveDocument(doc.id)}
                          disabled={approving[doc.id]}
                          className="rounded-md border border-green-600 px-2.5 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
                        >
                          {approving[doc.id] ? "…" : "Approve"}
                        </button>
                      )}
                      <button
                        onClick={() => deleteDocument(doc.id, doc.title)}
                        disabled={deleting[doc.id]}
                        className="rounded-md border border-red-200 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                      >
                        {deleting[doc.id] ? "…" : "Delete"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="border-t px-4 py-2 text-xs text-gray-400">
            {sorted.length} document{sorted.length !== 1 ? "s" : ""}
          </div>
        </div>
      )}
    </div>
  );
}
