import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { apiServer } from "@/lib/api";
import type { RFP, RFPQuestion, RFPAnswer } from "@/lib/api";
import RFPWorkspace from "./RFPWorkspace";

interface PageProps {
  params: { id: string };
}

export default async function RFPDetailPage({ params }: PageProps) {
  const cookieStore = cookies();
  const token = cookieStore.get("access_token")?.value ?? "";

  let rfp: RFP;
  let questions: RFPQuestion[];
  let answers: Map<string, RFPAnswer>;

  try {
    [rfp, questions] = await Promise.all([
      apiServer.getRFP(params.id, token),
      apiServer.listRFPQuestions(params.id, token),
    ]);

    const answerResults = await Promise.all(
      questions.map((q) =>
        apiServer.getLatestAnswer(params.id, q.id, token).catch(() => null)
      )
    );

    answers = new Map(
      questions.map((q, i) => [q.id, answerResults[i]] as [string, RFPAnswer])
    );
  } catch {
    notFound();
  }

  return (
    <RFPWorkspace
      rfp={rfp!}
      questions={questions!}
      initialAnswers={Object.fromEntries(answers!)}
      token={token}
    />
  );
}
