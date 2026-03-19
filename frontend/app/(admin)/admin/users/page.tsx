"use client";

import { useEffect, useState } from "react";
import type { User } from "@/lib/api";

const ROLES = ["end_user", "content_admin", "system_admin"] as const;

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Create form state
  const [showForm, setShowForm] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState<string>("end_user");
  const [newTeams, setNewTeams] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/users", { credentials: "include" })
      .then(async (res) => {
        if (!res.ok) throw new Error("Failed to fetch users");
        return res.json() as Promise<User[]>;
      })
      .then(setUsers)
      .catch((err) => setFetchError(err instanceof Error ? err.message : "Error"))
      .finally(() => setLoading(false));
  }, []);

  async function createUser() {
    setCreateError(null);
    setCreating(true);
    try {
      const teams = newTeams
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: newEmail, role: newRole, teams }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        setCreateError(data.detail ?? "Failed to create user");
        return;
      }
      const created = (await res.json()) as User;
      setUsers((prev) => [...prev, created]);
      setNewEmail("");
      setNewRole("end_user");
      setNewTeams("");
      setShowForm(false);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Users</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          {showForm ? "Cancel" : "Create User"}
        </button>
      </div>

      {showForm && (
        <div className="mb-6 rounded-xl border p-4 space-y-3">
          <h2 className="font-semibold">New User</h2>
          <input
            type="email"
            placeholder="Email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Teams (comma-separated)"
            value={newTeams}
            onChange={(e) => setNewTeams(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          {createError && (
            <p className="text-sm text-destructive">{createError}</p>
          )}
          <button
            onClick={createUser}
            disabled={creating || !newEmail}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create"}
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : fetchError ? (
        <p className="text-destructive">{fetchError}</p>
      ) : (
        <div className="overflow-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Email</th>
                <th className="px-4 py-3 text-left font-medium">Role</th>
                <th className="px-4 py-3 text-left font-medium">Name</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-muted/20">
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-secondary px-2 py-0.5 text-xs">
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {u.name ?? "—"}
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
