"use client";

import { useState, useEffect, FormEvent } from "react";
import { useRouter } from "next/navigation";
import type { Company } from "@/lib/api";

const INDUSTRIES = [
  "Financial Services",
  "Healthcare & Life Sciences",
  "Government & Public Sector",
  "Technology",
  "Manufacturing",
  "Retail & E-Commerce",
  "Energy & Utilities",
  "Education",
  "Telecommunications",
  "Professional Services",
  "Other",
];

const REGIONS = [
  "North America",
  "Europe (EMEA)",
  "Asia Pacific (APAC)",
  "Latin America",
  "Middle East & Africa",
  "Global",
];

export default function NewRFPPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [customer, setCustomer] = useState("");
  const [customCustomer, setCustomCustomer] = useState("");
  const [industry, setIndustry] = useState("");
  const [region, setRegion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/companies", { credentials: "include" })
      .then((r) => r.json())
      .then((data) => setCompanies(data as Company[]))
      .catch(() => {/* non-critical */});
  }, []);

  // Use custom name if "Other" selected or no companies loaded
  const effectiveCustomer = customer === "__custom__" ? customCustomer : customer;

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!effectiveCustomer.trim()) {
      setError("Please enter or select a customer name.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/rfps", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          customer: effectiveCustomer.trim(),
          industry,
          region,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError((data as { detail?: string }).detail ?? "Failed to create RFP.");
        return;
      }

      const created = (await res.json()) as { rfp_id: string };
      router.push(`/rfps/${created.rfp_id}`);
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">New RFP</h1>
        <p className="mt-1 text-sm text-gray-500">
          Create a new Request for Proposal workspace. You can add questions and generate
          AI-powered draft answers once the RFP is created.
        </p>
      </div>

      <div className="rounded-xl border bg-white p-6 shadow-sm">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="customer" className="mb-1 block text-sm font-medium text-gray-700">
              Customer / Organization <span className="text-red-500">*</span>
            </label>
            {companies.length > 0 ? (
              <>
                <select
                  id="customer"
                  required={customer !== "__custom__"}
                  value={customer}
                  onChange={(e) => setCustomer(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                >
                  <option value="">Select a company…</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                  <option value="__custom__">Other (enter manually)</option>
                </select>
                {customer === "__custom__" && (
                  <input
                    type="text"
                    required
                    placeholder="Enter company name"
                    value={customCustomer}
                    onChange={(e) => setCustomCustomer(e.target.value)}
                    className="mt-2 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                  />
                )}
                <p className="mt-1 text-xs text-gray-400">
                  Manage the company list under Admin → Companies.
                </p>
              </>
            ) : (
              <input
                id="customer"
                type="text"
                required
                value={customer}
                onChange={(e) => setCustomer(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                placeholder="e.g. Acme Corporation"
              />
            )}
          </div>

          <div>
            <label htmlFor="industry" className="mb-1 block text-sm font-medium text-gray-700">
              Industry <span className="text-red-500">*</span>
            </label>
            <select
              id="industry"
              required
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            >
              <option value="">Select an industry…</option>
              {INDUSTRIES.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="region" className="mb-1 block text-sm font-medium text-gray-700">
              Region <span className="text-red-500">*</span>
            </label>
            <select
              id="region"
              required
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            >
              <option value="">Select a region…</option>
              {REGIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "Creating…" : "Create RFP"}
            </button>
            <button
              type="button"
              onClick={() => router.back()}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
