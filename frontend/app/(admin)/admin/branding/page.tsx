"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getTenant,
  patchBrand,
  getScoreBoosts,
  type Tenant,
  type TenantBrand,
  type ScoreBoosts,
} from "@/lib/api";
import { formatPercent } from "@/lib/format";

export default function BrandingPage() {
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // form state
  const [primary, setPrimary] = useState("#1d4ed8");
  const [accent, setAccent] = useState("#9333ea");
  const [logoUrl, setLogoUrl] = useState("");
  const [reportHeader, setReportHeader] = useState("");
  const [reportFooter, setReportFooter] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // boosts
  const [boosts, setBoosts] = useState<ScoreBoosts | null>(null);
  const [boostsError, setBoostsError] = useState<string | null>(null);

  const applyTenant = useCallback((t: Tenant) => {
    setTenant(t);
    const b = t.brand ?? {};
    if (b.primary_color) setPrimary(b.primary_color);
    if (b.accent_color) setAccent(b.accent_color);
    setLogoUrl(b.logo_url ?? "");
    setReportHeader(b.report_header ?? "");
    setReportFooter(b.report_footer ?? "");
  }, []);

  const refresh = useCallback(() => {
    setLoading(true);
    getTenant()
      .then((t) => {
        applyTenant(t);
        setError(null);
        return getScoreBoosts(t.id).then(
          (b) => {
            setBoosts(b);
            setBoostsError(null);
          },
          (err: unknown) =>
            setBoostsError(err instanceof Error ? err.message : "Failed to load boosts")
        );
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load tenant")
      )
      .finally(() => setLoading(false));
  }, [applyTenant]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const body: TenantBrand = {};
      if (primary.trim()) body.primary_color = primary.trim();
      if (accent.trim()) body.accent_color = accent.trim();
      if (logoUrl.trim()) body.logo_url = logoUrl.trim();
      if (reportHeader.trim()) body.report_header = reportHeader.trim();
      if (reportFooter.trim()) body.report_footer = reportFooter.trim();
      await patchBrand(body);
      setSaved(true);
      refresh();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Branding</h1>
        <p className="mt-1 text-sm text-gray-500">
          Tenant-level colors, logo, and report chrome. Used across the app and exported PDFs.
        </p>
      </div>

      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {error && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
          {error}
        </div>
      )}

      {tenant && (
        <form
          onSubmit={save}
          className="mb-6 space-y-4 rounded-xl border bg-white p-4 shadow-sm"
        >
          <div>
            <h2 className="font-semibold text-gray-800">{tenant.display_name}</h2>
            <p className="text-xs text-gray-500">{tenant.slug}</p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-gray-600">
                Primary color
              </span>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={primary}
                  onChange={(e) => setPrimary(e.target.value)}
                  className="h-10 w-14 cursor-pointer rounded border"
                />
                <input
                  value={primary}
                  onChange={(e) => setPrimary(e.target.value)}
                  className="flex-1 rounded-md border px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-gray-600">
                Accent color
              </span>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={accent}
                  onChange={(e) => setAccent(e.target.value)}
                  className="h-10 w-14 cursor-pointer rounded border"
                />
                <input
                  value={accent}
                  onChange={(e) => setAccent(e.target.value)}
                  className="flex-1 rounded-md border px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                />
              </div>
            </label>
          </div>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-600">
              Logo URL
            </span>
            <input
              value={logoUrl}
              onChange={(e) => setLogoUrl(e.target.value)}
              placeholder="https://…/logo.svg"
              className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-600">
              Report header
            </span>
            <input
              value={reportHeader}
              onChange={(e) => setReportHeader(e.target.value)}
              placeholder="Header text shown at the top of exported PDFs"
              className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-600">
              Report footer
            </span>
            <input
              value={reportFooter}
              onChange={(e) => setReportFooter(e.target.value)}
              placeholder="Footer text shown at the bottom of exported PDFs"
              className="w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </label>

          {saveError && <p className="text-xs text-rose-600">{saveError}</p>}
          {saved && <p className="text-xs text-emerald-600">Saved.</p>}
          <div className="flex items-center justify-between gap-4">
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save"}
            </button>

            <div className="flex items-center gap-3 text-xs text-gray-500">
              <span>Preview:</span>
              <span
                className="inline-block h-7 w-7 rounded-full border"
                style={{ backgroundColor: primary }}
                title={`Primary ${primary}`}
              />
              <span
                className="inline-block h-7 w-7 rounded-full border"
                style={{ backgroundColor: accent }}
                title={`Accent ${accent}`}
              />
            </div>
          </div>
        </form>
      )}

      {/* Learning status */}
      <section className="rounded-xl border bg-white p-4 shadow-sm">
        <header className="mb-2 flex items-baseline justify-between">
          <h2 className="font-semibold text-gray-900">Learning status</h2>
          {boosts && (
            <span className="text-xs text-gray-500">
              {boosts.n_total_proposals} total proposals tracked
            </span>
          )}
        </header>
        {boosts && (
          <p className="mb-3 text-xs text-gray-500">
            Patterns with n_total &lt; {boosts.min_n} are gated and emit zero boost — honest about
            cold-start.
          </p>
        )}
        {boostsError && (
          <p className="text-xs text-rose-600">{boostsError}</p>
        )}
        {boosts && boosts.patterns.length === 0 && (
          <p className="py-4 text-center text-xs text-gray-500">
            No industry patterns yet. Add past proposals to start learning.
          </p>
        )}
        {boosts && boosts.patterns.length > 0 && (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Industry</th>
                  <th className="px-3 py-2 text-right font-medium">N</th>
                  <th className="px-3 py-2 text-right font-medium">Won</th>
                  <th className="px-3 py-2 text-right font-medium">Win rate</th>
                  <th className="px-3 py-2 text-right font-medium">Boost</th>
                  <th className="px-3 py-2 text-left font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {boosts.patterns.map((p) => (
                  <tr key={p.industry_id}>
                    <td className="px-3 py-2 text-gray-800">
                      {p.industry_name ?? p.industry_id}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-700">{p.n_total}</td>
                    <td className="px-3 py-2 text-right font-mono text-gray-700">{p.n_won}</td>
                    <td className="px-3 py-2 text-right font-mono text-gray-700">
                      {formatPercent(p.win_rate)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-700">
                      {p.boost.toFixed(3)}
                    </td>
                    <td className="px-3 py-2">
                      {p.active ? (
                        <span className="inline-flex rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                          active
                        </span>
                      ) : (
                        <span className="inline-flex rounded-full bg-gray-200 px-2 py-0.5 text-xs font-medium text-gray-700">
                          gated
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
