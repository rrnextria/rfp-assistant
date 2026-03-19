import Link from "next/link";
import { cookies } from "next/headers";
import { apiServer } from "@/lib/api";
import type { RFP } from "@/lib/api";

export default async function RFPsPage() {
  const cookieStore = cookies();
  const token = cookieStore.get("access_token")?.value ?? "";

  let rfps: RFP[] = [];
  let fetchError: string | null = null;

  try {
    rfps = await apiServer.listRFPs(token);
  } catch (err) {
    fetchError = err instanceof Error ? err.message : "Failed to load RFPs.";
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">RFPs</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage Requests for Proposals. Open an RFP to view its questions and AI-generated answers.
          </p>
        </div>
        <Link
          href="/rfps/new"
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition-colors"
        >
          + New RFP
        </Link>
      </div>

      {/* Help callout */}
      <div className="mb-6 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800">
        <strong>Tip:</strong> Use the <Link href="/ask" className="underline font-medium">Ask AI</Link> page
        to query your product knowledge base with free-form questions, or open an RFP below to generate
        and manage structured draft answers for each requirement.
      </div>

      {fetchError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {fetchError}
        </div>
      )}

      {rfps.length === 0 && !fetchError ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center">
          <p className="text-4xl mb-3">📋</p>
          <h3 className="text-base font-semibold text-gray-900">No RFPs yet</h3>
          <p className="mt-1 text-sm text-gray-500">
            Create your first RFP to start generating AI-powered draft answers.
          </p>
          <Link
            href="/rfps/new"
            className="mt-4 inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            Create RFP
          </Link>
        </div>
      ) : (
        <div className="divide-y rounded-xl border bg-white shadow-sm">
          {rfps.map((rfp) => (
            <Link
              key={rfp.id}
              href={`/rfps/${rfp.id}`}
              className="flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition-colors first:rounded-t-xl last:rounded-b-xl"
            >
              <div>
                <p className="font-semibold text-gray-900">{rfp.customer}</p>
                <p className="text-sm text-gray-500 mt-0.5">
                  {rfp.industry} · {rfp.region}
                </p>
              </div>
              <span className="text-sm font-medium text-blue-600">View →</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
