"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listSnippets,
  createSnippet,
  deleteSnippet,
  type Snippet,
} from "@/lib/api";

export default function SnippetsPage() {
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tagsInput, setTagsInput] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    listSnippets()
      .then((items) => {
        setSnippets(items);
        setError(null);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load snippets")
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !body.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const topic_tags = tagsInput
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await createSnippet({ title: title.trim(), body: body.trim(), topic_tags });
      setTitle("");
      setBody("");
      setTagsInput("");
      refresh();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create snippet");
    } finally {
      setCreating(false);
    }
  }

  async function archive(id: string) {
    if (!confirm("Archive this snippet?")) return;
    try {
      await deleteSnippet(id);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Archive failed");
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Snippet library</h1>
        <p className="mt-1 text-sm text-gray-500">
          Reusable corporate-response snippets surfaced as suggestions during bid assessment.
        </p>
      </div>

      <form
        onSubmit={add}
        className="mb-6 space-y-3 rounded-xl border bg-white p-4 shadow-sm"
      >
        <h2 className="font-semibold text-gray-800">New snippet</h2>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title (e.g. SOC 2 compliance statement)"
          className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Body — the canonical paragraph to drop into a proposal."
          rows={5}
          className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        <input
          value={tagsInput}
          onChange={(e) => setTagsInput(e.target.value)}
          placeholder="Comma-separated topic tags (gdpr, soc2, encryption)"
          className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        {createError && <p className="text-xs text-rose-600">{createError}</p>}
        <button
          type="submit"
          disabled={creating || !title.trim() || !body.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {creating ? "Adding…" : "Add snippet"}
        </button>
      </form>

      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {error && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
          {error}
        </div>
      )}

      {!loading && snippets.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center">
          <p className="font-semibold text-gray-900">No snippets yet</p>
          <p className="mt-1 text-sm text-gray-500">Add your first snippet above.</p>
        </div>
      )}

      <ul className="divide-y rounded-xl border bg-white shadow-sm">
        {snippets.map((s) => (
          <li key={s.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <h3 className="font-semibold text-gray-900">{s.title}</h3>
                <p className="mt-1 whitespace-pre-wrap text-sm text-gray-700">
                  {s.body.length > 240 ? `${s.body.slice(0, 240)}…` : s.body}
                </p>
                <p className="mt-2 text-xs text-gray-500">
                  Tags: {(s.metadata?.topic_tags ?? []).join(", ") || "—"} · v
                  {s.metadata?.version ?? 1} · {s.status}
                </p>
              </div>
              {s.status !== "archived" && (
                <button
                  onClick={() => archive(s.id)}
                  className="text-xs font-medium text-rose-600 hover:text-rose-700"
                >
                  Archive
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
