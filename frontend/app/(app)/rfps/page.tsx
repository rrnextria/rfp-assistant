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
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">RFPs</h1>
        <Link
          href="/rfps/new"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          New RFP
        </Link>
      </div>

      {fetchError && (
        <p className="mb-4 text-sm text-destructive">{fetchError}</p>
      )}

      {rfps.length === 0 && !fetchError ? (
        <p className="text-muted-foreground">No RFPs yet. Create one to get started.</p>
      ) : (
        <div className="divide-y rounded-xl border">
          {rfps.map((rfp) => (
            <Link
              key={rfp.id}
              href={`/rfps/${rfp.id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-muted/40"
            >
              <div>
                <p className="font-medium">{rfp.customer}</p>
                <p className="text-sm text-muted-foreground">
                  {rfp.industry} · {rfp.region}
                </p>
              </div>
              <span className="text-xs text-muted-foreground">View →</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
