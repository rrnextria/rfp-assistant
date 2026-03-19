"use client";

import { useEffect, useState, KeyboardEvent } from "react";
import type { User } from "@/lib/api";

const ROLE_OPTIONS = [
  { value: "end_user", label: "End User — can query the knowledge base and manage their own RFPs" },
  { value: "content_admin", label: "Content Admin — can also upload and approve documents" },
  { value: "system_admin", label: "System Admin — full access including user management" },
] as const;

const ROLE_LABEL: Record<string, string> = {
  end_user: "End User",
  content_admin: "Content Admin",
  system_admin: "System Admin",
};

const ROLE_BADGE: Record<string, string> = {
  end_user: "bg-gray-100 text-gray-600",
  content_admin: "bg-blue-100 text-blue-700",
  system_admin: "bg-purple-100 text-purple-700",
};

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Create form state
  const [showForm, setShowForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<string>("end_user");
  const [teamInput, setTeamInput] = useState("");
  const [newTeams, setNewTeams] = useState<string[]>([]);
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

  function addTeam() {
    const t = teamInput.trim();
    if (t && !newTeams.includes(t)) {
      setNewTeams((prev) => [...prev, t]);
    }
    setTeamInput("");
  }

  function removeTeam(team: string) {
    setNewTeams((prev) => prev.filter((t) => t !== team));
  }

  function handleTeamKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTeam();
    }
  }

  async function createUser() {
    setCreateError(null);
    setCreating(true);
    try {
      const res = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: newEmail,
          name: newName || undefined,
          role: newRole,
          teams: newTeams,
          password: newPassword,
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        setCreateError(data.detail ?? "Failed to create user");
        return;
      }
      const created = (await res.json()) as { user_id: string };
      // Refresh user list
      const refreshed = await fetch("/api/users", { credentials: "include" }).then(
        (r) => r.json() as Promise<User[]>
      );
      setUsers(refreshed);
      setNewName("");
      setNewEmail("");
      setNewPassword("");
      setNewRole("end_user");
      setNewTeams([]);
      setTeamInput("");
      setShowForm(false);
    } finally {
      setCreating(false);
    }
  }

  function cancelForm() {
    setShowForm(false);
    setNewName("");
    setNewEmail("");
    setNewPassword("");
    setNewRole("end_user");
    setNewTeams([]);
    setTeamInput("");
    setCreateError(null);
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Users</h1>
            <p className="mt-1 text-sm text-gray-500">
              Manage who has access to RFP Assistant and what they can do.
            </p>
          </div>
          {!showForm && (
            <button
              onClick={() => setShowForm(true)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition-colors"
            >
              + Add User
            </button>
          )}
        </div>
      </div>

      {showForm && (
        <div className="mb-8 rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-semibold text-gray-800">New User</h2>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  Full Name
                </label>
                <input
                  type="text"
                  placeholder="Jane Smith"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  Email Address <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  placeholder="jane@company.com"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Password <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                placeholder="Minimum 8 characters"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Role <span className="text-red-500">*</span>
              </label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Teams
              </label>
              <p className="mb-2 text-xs text-gray-500">
                Assign this user to one or more teams. Type a team name and press Enter.
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="e.g. Engineering, Sales, Pre-Sales"
                  value={teamInput}
                  onChange={(e) => setTeamInput(e.target.value)}
                  onKeyDown={handleTeamKeyDown}
                  className="flex-1 rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                />
                <button
                  type="button"
                  onClick={addTeam}
                  disabled={!teamInput.trim()}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                >
                  Add
                </button>
              </div>
              {newTeams.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {newTeams.map((t) => (
                    <span
                      key={t}
                      className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800"
                    >
                      {t}
                      <button
                        onClick={() => removeTeam(t)}
                        className="ml-0.5 text-blue-500 hover:text-blue-700"
                        aria-label={`Remove ${t}`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {createError && <p className="text-sm text-red-600">{createError}</p>}

            <div className="flex gap-3 pt-1">
              <button
                onClick={createUser}
                disabled={creating || !newEmail || !newPassword}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {creating ? "Creating…" : "Create User"}
              </button>
              <button
                onClick={cancelForm}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-gray-500">Loading users…</p>
      ) : fetchError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {fetchError}
        </div>
      ) : users.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center">
          <p className="text-4xl mb-3">👥</p>
          <p className="font-semibold text-gray-900">No users yet</p>
          <p className="text-sm text-gray-500 mt-1">Add the first user above.</p>
        </div>
      ) : (
        <div className="overflow-auto rounded-xl border bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3 text-left">Name</th>
                <th className="px-4 py-3 text-left">Email</th>
                <th className="px-4 py-3 text-left">Role</th>
                <th className="px-4 py-3 text-left">Teams</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {u.name ?? <span className="text-gray-400 italic">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-700">{u.email}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        ROLE_BADGE[u.role] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {ROLE_LABEL[u.role] ?? u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {u.teams && u.teams.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {u.teams.map((t) => (
                          <span
                            key={t}
                            className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-gray-400 italic text-xs">No teams</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="border-t px-4 py-2 text-xs text-gray-400">
            {users.length} user{users.length !== 1 ? "s" : ""}
          </div>
        </div>
      )}
    </div>
  );
}
