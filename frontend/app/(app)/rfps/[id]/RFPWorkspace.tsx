"use client";

import type { RFP, RFPQuestion, RFPAnswer } from "@/lib/api";
import { RFPHeader } from "@/components/rfp/RFPHeader";
import { AssessmentScorecard } from "@/components/rfp/AssessmentScorecard";
import { DraftSection } from "@/components/rfp/DraftSection";

interface Props {
  rfp: RFP;
  // Retained for back-compat with the server-rendered page wrapper.
  // DraftSection now fetches its own data via the rewrite proxy.
  questions?: RFPQuestion[];
  initialAnswers?: Record<string, RFPAnswer | null>;
  token?: string;
}

/**
 * Single-page RFP workspace:
 *  - RFPHeader        (title, client, industry, region, status)
 *  - AssessmentScorecard (verdict + 4 panels + summary)
 *  - DraftSection     (existing answer-drafting UI)
 *
 * Stacked vertically on a single scrollable page. No tabs, no stepper.
 */
export default function RFPWorkspace({ rfp }: Props) {
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6">
      <RFPHeader
        title={rfp.customer}
        client={rfp.customer}
        industry={rfp.industry}
        region={rfp.region}
        status={rfp.status}
      />
      <AssessmentScorecard rfpId={rfp.id} />
      <DraftSection rfpId={rfp.id} />
    </div>
  );
}
