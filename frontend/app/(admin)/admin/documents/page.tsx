"use client";

import { useEffect, useRef, useState } from "react";
import type { Document } from "@/lib/api";

export default function AdminDocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [approving, setApproving] = useState<Record<string, boolean>>({});

  // Upload form state
  const fileRef = useRef<HTMLInputElement>(null);
  const [product, setProduct] = useState("");
  const [region, setRegion] = useState("");
  const [industry, setIndustry] = useState("");
  const [allowedTeams, setAllowedTeams] = useState("");
  const [allowedRoles, setAllowedRoles] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/documents", { credentials: "include" })
      .then(async (res) => {
        if (!res.ok) throw new Error("Failed to fetch documents");
        return res.json() as Promise<Document[]>;
      })
      .then(setDocuments)
      .catch((err) => setFetchError(err instanceof Error ? err.message : "Error"))
      .finally(() => setLoading(false));
  }, []);

  async function uploadDocument() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    setUploadError(null);
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
          allowed_teams: allowedTeams.split(",").map((t) => t.trim()).filter(Boolean),
          allowed_roles: allowedRoles.split(",").map((r) => r.trim()).filter(Boolean),
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

      const uploaded = (await res.json()) as Document;
      setDocuments((prev) => [uploaded, ...prev]);
      setProduct("");
      setRegion("");
      setIndustry("");
      setAllowedTeams("");
      setAllowedRoles("");
      if (fileRef.current) fileRef.current.value = "";
    } finally {
      setUploading(false);
    }
  }

  async function approveDocument(docId: string) {
    setApproving((prev) => ({ ...prev, [docId]: true }));
    try {
      const res = await fetch(`/api/documents/${docId}/approve`, {
        method: "PATCH",
        credentials: "include",
      });
      if (res.ok) {
        const updated = (await res.json()) as Document;
        setDocuments((prev) => prev.map((d) => (d.id === docId ? updated : d)));
      }
    } finally {
      setApproving((prev) => ({ ...prev, [docId]: false }));
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Documents</h1>

      {/* Upload form */}
      <div className="mb-8 rounded-xl border p-4 space-y-3">
        <h2 className="font-semibold">Upload Document</h2>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx"
          className="block w-full text-sm text-muted-foreground file:mr-4 file:rounded-md file:border-0 file:bg-primary file:px-4 file:py-2 file:text-xs file:font-medium file:text-primary-foreground"
        />
        <div className="grid grid-cols-2 gap-3">
          <input
            type="text"
            placeholder="Product"
            value={product}
            onChange={(e) => setProduct(e.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            type="text"
            placeholder="Region"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            type="text"
            placeholder="Industry"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            type="text"
            placeholder="Allowed teams (comma-sep)"
            value={allowedTeams}
            onChange={(e) => setAllowedTeams(e.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            type="text"
            placeholder="Allowed roles (comma-sep)"
            value={allowedRoles}
            onChange={(e) => setAllowedRoles(e.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        {uploadError && <p className="text-sm text-destructive">{uploadError}</p>}
        <button
          onClick={uploadDocument}
          disabled={uploading}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {uploading ? "Uploading…" : "Upload"}
        </button>
      </div>

      {/* Document list */}
      {loading ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : fetchError ? (
        <p className="text-destructive">{fetchError}</p>
      ) : (
        <div className="overflow-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Title</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Version</th>
                <th className="px-4 py-3 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-muted/20">
                  <td className="px-4 py-3 font-medium">{doc.title}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        doc.status === "approved"
                          ? "bg-green-100 text-green-800"
                          : "bg-yellow-100 text-yellow-800"
                      }`}
                    >
                      {doc.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{doc.version}</td>
                  <td className="px-4 py-3">
                    {doc.status !== "approved" && (
                      <button
                        onClick={() => approveDocument(doc.id)}
                        disabled={approving[doc.id]}
                        className="rounded-md border border-green-600 px-3 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
                      >
                        {approving[doc.id] ? "Approving…" : "Approve"}
                      </button>
                    )}
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
