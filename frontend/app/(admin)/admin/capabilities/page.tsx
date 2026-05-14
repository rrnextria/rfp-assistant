"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getCapabilityProfile,
  createIndustry,
  deleteIndustry,
  createGeography,
  deleteGeography,
  createCertification,
  deleteCertification,
  createServiceLine,
  deleteServiceLine,
  type CapabilityProfile,
} from "@/lib/api";

type Dimension = "industries" | "geographies" | "certifications" | "service_lines";

const HANDLERS: Record<
  Dimension,
  { create: (name: string) => Promise<unknown>; remove: (id: string) => Promise<void>; label: string }
> = {
  industries: { create: createIndustry, remove: deleteIndustry, label: "Industries" },
  geographies: { create: createGeography, remove: deleteGeography, label: "Geographies" },
  certifications: { create: createCertification, remove: deleteCertification, label: "Certifications" },
  service_lines: {
    create: (name: string) => createServiceLine(name),
    remove: deleteServiceLine,
    label: "Service lines",
  },
};

export default function CapabilitiesPage() {
  const [profile, setProfile] = useState<CapabilityProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    getCapabilityProfile()
      .then((p) => {
        setProfile(p);
        setError(null);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load capabilities")
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Capability profile</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage the tenant&apos;s industries, geographies, certifications, and service lines. These
          drive bid eligibility and best-fit scoring.
        </p>
      </div>
      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {error && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
          {error}
        </div>
      )}
      {profile && (
        <div className="space-y-4">
          <DimensionSection
            dimension="industries"
            items={profile.industries.map((i) => ({ id: i.id, name: i.name }))}
            onChanged={refresh}
          />
          <DimensionSection
            dimension="geographies"
            items={profile.geographies.map((i) => ({ id: i.id, name: i.name }))}
            onChanged={refresh}
          />
          <DimensionSection
            dimension="certifications"
            items={profile.certifications.map((i) => ({ id: i.id, name: i.name }))}
            onChanged={refresh}
          />
          <DimensionSection
            dimension="service_lines"
            items={profile.service_lines.map((i) => ({ id: i.id, name: i.name }))}
            onChanged={refresh}
          />
        </div>
      )}
    </div>
  );
}

interface DimensionSectionProps {
  dimension: Dimension;
  items: { id: string; name: string }[];
  onChanged: () => void;
}

function DimensionSection({ dimension, items, onChanged }: DimensionSectionProps) {
  const handler = HANDLERS[dimension];
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function add() {
    const name = draft.trim();
    if (!name) return;
    setBusy(true);
    setErr(null);
    try {
      await handler.create(name);
      setDraft("");
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "create failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setErr(null);
    try {
      await handler.remove(id);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "delete failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border bg-white p-4 shadow-sm">
      <h2 className="mb-2 font-semibold text-gray-900">{handler.label}</h2>
      {items.length === 0 ? (
        <p className="py-2 text-xs text-gray-500">No entries yet.</p>
      ) : (
        <ul className="divide-y">
          {items.map((it) => (
            <li key={it.id} className="flex items-center justify-between py-2 text-sm">
              <span className="text-gray-800">{it.name}</span>
              <button
                onClick={() => remove(it.id)}
                disabled={busy}
                className="text-xs font-medium text-rose-600 hover:text-rose-700 disabled:opacity-50"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder={`New ${handler.label.toLowerCase().replace(/s$/, "")}…`}
          className="flex-1 rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        <button
          onClick={add}
          disabled={busy || !draft.trim()}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Add
        </button>
      </div>
      {err && <p className="mt-2 text-xs text-rose-600">{err}</p>}
    </section>
  );
}
