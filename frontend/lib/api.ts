/**
 * Typed API client for the RFP Assistant backend.
 * Browser-side calls go to /api/* (proxied to api-gateway via next.config.js rewrites).
 * Server-side calls (React Server Components) use the full NEXT_PUBLIC_API_URL base URL.
 */

// ─── Types ────────────────────────────────────────────────────────────────────

export type AskMode = "answer" | "draft" | "review" | "gap";

export interface Citation {
  chunk_id: string;
  doc_id: string;
  doc_title?: string;
  snippet: string;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  partial_compliance?: boolean;
}

export interface User {
  id: string;
  email: string;
  name?: string;
  role: string;
  teams?: string[];
  created_at?: string;
}

export interface RFP {
  id: string;
  customer: string;
  industry: string;
  region: string;
  status?: string;
  created_at?: string;
  created_by?: string;
}

export interface Company {
  id: string;
  name: string;
}

export interface RFPQuestion {
  id: string;
  rfp_id: string;
  question: string;
}

export interface RFPAnswer {
  id: string;
  question_id: string;
  answer: string;
  approved: boolean;
  version: number;
}

export interface Document {
  id: string;
  title: string;
  status: string;
  created_by?: string;
  created_at?: string;
  version?: number;
}

// ─── Client-side helpers (browser) ───────────────────────────────────────────

const API_BASE =
  typeof window !== "undefined"
    ? "/api" // browser: use Next.js rewrite proxy
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"); // server

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    credentials: "include",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    let message = `API error ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  return res.json() as Promise<T>;
}

// ─── Public browser API ────────────────────────────────────────────────────────

export const api = {
  // Auth
  login(email: string, password: string): Promise<{ access_token: string }> {
    return apiFetch("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  logout(): Promise<void> {
    return apiFetch("/auth/logout", { method: "POST" });
  },

  // Ask (non-streaming)
  ask(payload: {
    question: string;
    mode: AskMode;
    rfp_id?: string;
  }): Promise<AskResponse> {
    return apiFetch("/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Users
  listUsers(): Promise<User[]> {
    return apiFetch("/users");
  },

  createUser(payload: {
    email: string;
    role: string;
    teams?: string[];
  }): Promise<User> {
    return apiFetch("/users", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Documents
  listDocuments(): Promise<Document[]> {
    return apiFetch("/documents");
  },

  uploadDocument(formData: FormData): Promise<Document> {
    // Do not set Content-Type — browser sets it with boundary for multipart
    return fetch(`${API_BASE}/documents`, {
      method: "POST",
      credentials: "include",
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `Upload failed: ${res.status}`);
      }
      return res.json() as Promise<Document>;
    });
  },

  approveDocument(docId: string): Promise<Document> {
    return apiFetch(`/documents/${docId}/approve`, { method: "PATCH" });
  },

  deleteDocument(docId: string): Promise<void> {
    return apiFetch(`/documents/${docId}`, { method: "DELETE" });
  },

  // RFPs
  listRFPs(): Promise<RFP[]> {
    return apiFetch("/rfps");
  },

  getRFP(id: string): Promise<RFP> {
    return apiFetch(`/rfps/${id}`);
  },

  createRFP(payload: {
    customer: string;
    industry: string;
    region: string;
  }): Promise<{ rfp_id: string }> {
    return apiFetch("/rfps", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateRFP(id: string, payload: { status?: string; customer?: string }): Promise<{ rfp_id: string; updated: boolean }> {
    return apiFetch(`/rfps/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  deleteRFP(id: string): Promise<void> {
    return apiFetch(`/rfps/${id}`, { method: "DELETE" });
  },

  regenerateAllAnswers(rfpId: string): Promise<{ status: string; rfp_id: string }> {
    return apiFetch(`/rfps/${rfpId}/regenerate-all`, {
      method: "POST",
      body: JSON.stringify({ detail_level: "balanced", user_context: {} }),
    });
  },

  // Companies
  listCompanies(): Promise<Company[]> {
    return apiFetch("/companies");
  },

  createCompany(name: string): Promise<{ company_id: string; name: string }> {
    return apiFetch("/companies", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  },

  deleteCompany(id: string): Promise<void> {
    return apiFetch(`/companies/${id}`, { method: "DELETE" });
  },

  // RFP Questions
  listRFPQuestions(rfpId: string): Promise<RFPQuestion[]> {
    return apiFetch(`/rfps/${rfpId}/questions`);
  },

  addRFPQuestion(rfpId: string, question: string): Promise<RFPQuestion> {
    return apiFetch(`/rfps/${rfpId}/questions`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  },

  // RFP Answers
  getLatestAnswer(rfpId: string, questionId: string): Promise<RFPAnswer> {
    return apiFetch(`/rfps/${rfpId}/questions/${questionId}/answers/latest`);
  },

  createAnswer(rfpId: string, questionId: string, answer: string): Promise<RFPAnswer> {
    return apiFetch(`/rfps/${rfpId}/questions/${questionId}/answers`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    });
  },

  patchAnswer(
    rfpId: string,
    questionId: string,
    answerId: string,
    answer: string
  ): Promise<RFPAnswer> {
    return apiFetch(`/rfps/${rfpId}/questions/${questionId}/answers/${answerId}`, {
      method: "PATCH",
      body: JSON.stringify({ answer }),
    });
  },

  approveAnswer(
    rfpId: string,
    questionId: string,
    answerId: string
  ): Promise<RFPAnswer> {
    return apiFetch(
      `/rfps/${rfpId}/questions/${questionId}/answers/${answerId}/approve`,
      { method: "POST" }
    );
  },
};

// ─── Server-side API (React Server Components) ────────────────────────────────
// These functions accept a token and call the API directly (no cookie on server).

const serverBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function serverFetch<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${serverBase}${path}`, {
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });

  if (!res.ok) {
    let message = `API error ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  return res.json() as Promise<T>;
}

// ─── Bid Assessment / Capabilities / Snippets (browser) ──────────────────────

// Tenant + branding
export interface TenantBrand {
  primary_color?: string;
  accent_color?: string;
  logo_url?: string;
  report_header?: string;
  report_footer?: string;
}

export interface Tenant {
  id: string;
  slug: string;
  display_name: string;
  brand: TenantBrand;
  config?: Record<string, unknown>;
}

export async function getTenant(): Promise<Tenant> {
  return apiFetch<Tenant>("/tenants/me");
}

export async function patchBrand(brand: TenantBrand): Promise<{ brand: TenantBrand }> {
  return apiFetch<{ brand: TenantBrand }>("/tenants/me/brand", {
    method: "PATCH",
    body: JSON.stringify(brand),
  });
}

// Assessments
export type Verdict = "bid" | "no_bid" | "review";

export interface AssessmentHead {
  id: string;
  rfp_id?: string;
  version: number;
  status: string;
  verdict: Verdict | null;
  fit_score: number | null;
  win_probability: number | null;
  summary: string | null;
  created_at?: string;
  created_by?: string;
}

export interface ComplianceItem {
  id: string;
  label: string;
  category: string;
  mandatory: boolean;
  status: "pass" | "fail" | "partial" | "unknown";
  evidence: { kind?: string; ref_id?: string; excerpt?: string };
}

export interface EligibilityItem {
  id: string;
  label: string;
  kind: string;
  expected: string | null;
  actual: string | null;
  status: "pass" | "fail" | "partial" | "unknown";
}

export interface RiskItem {
  id: string;
  title: string;
  description?: string | null;
  severity: "low" | "medium" | "high" | "critical" | string;
  likelihood: "low" | "medium" | "high" | string;
  mitigation?: string | null;
}

export interface BestFitMatch {
  id: string;
  requirement: string;
  offering: string | null;
  match_score: number; // 0..100
  note?: string | null;
}

export interface AssessmentLatest {
  head: AssessmentHead;
  compliance: ComplianceItem[];
  eligibility: EligibilityItem[];
  risks: RiskItem[];
  best_fit: BestFitMatch[];
}

export interface AssessmentRunResponse {
  assessment_id: string;
  version: number;
  status: string;
  verdict: Verdict | null;
  fit_score: number | null;
  win_probability: number | null;
  summary: string | null;
}

export async function runAssessment(rfpId: string): Promise<AssessmentRunResponse> {
  return apiFetch<AssessmentRunResponse>(`/rfps/${rfpId}/assess`, { method: "POST" });
}

export async function getAssessmentLatest(rfpId: string): Promise<AssessmentLatest | null> {
  const url = `${API_BASE}/rfps/${rfpId}/assessments/latest`;
  const res = await fetch(url, { credentials: "include" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`assessment fetch failed (${res.status})`);
  return res.json() as Promise<AssessmentLatest>;
}

export async function listAssessments(rfpId: string): Promise<AssessmentHead[]> {
  return apiFetch<AssessmentHead[]>(`/rfps/${rfpId}/assessments`);
}

// Capabilities
export interface CapabilityItem {
  id: string;
  name: string;
}

export interface ServiceLine {
  id: string;
  name: string;
  description?: string | null;
}

export interface CapabilityProfile {
  service_lines: ServiceLine[];
  industries: CapabilityItem[];
  geographies: CapabilityItem[];
  certifications: CapabilityItem[];
  products: CapabilityItem[];
}

export async function getCapabilityProfile(): Promise<CapabilityProfile> {
  return apiFetch<CapabilityProfile>("/capabilities/profile");
}

async function capabilityCreate(resource: string, body: Record<string, unknown>) {
  return apiFetch<CapabilityItem | ServiceLine>(`/capabilities/${resource}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

async function capabilityDelete(resource: string, id: string): Promise<void> {
  const url = `${API_BASE}/capabilities/${resource}/${id}`;
  const res = await fetch(url, { method: "DELETE", credentials: "include" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`delete failed (${res.status})`);
  }
}

export const createIndustry = (name: string) => capabilityCreate("industries", { name });
export const deleteIndustry = (id: string) => capabilityDelete("industries", id);
export const createGeography = (name: string) => capabilityCreate("geographies", { name });
export const deleteGeography = (id: string) => capabilityDelete("geographies", id);
export const createCertification = (name: string) => capabilityCreate("certifications", { name });
export const deleteCertification = (id: string) => capabilityDelete("certifications", id);
export const createServiceLine = (name: string, description?: string) =>
  capabilityCreate("service-lines", { name, description });
export const deleteServiceLine = (id: string) => capabilityDelete("service-lines", id);

// Snippets
export interface Snippet {
  id: string;
  title: string;
  body: string;
  status: string;
  metadata?: {
    topic_tags?: string[];
    version?: number;
    [k: string]: unknown;
  };
  created_at?: string;
  updated_at?: string;
}

export interface SnippetInput {
  title: string;
  body: string;
  topic_tags?: string[];
}

export async function listSnippets(): Promise<Snippet[]> {
  return apiFetch<Snippet[]>("/snippets");
}

export async function createSnippet(input: SnippetInput): Promise<Snippet> {
  return apiFetch<Snippet>("/snippets", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function patchSnippet(id: string, input: Partial<SnippetInput>): Promise<Snippet> {
  return apiFetch<Snippet>(`/snippets/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function deleteSnippet(id: string): Promise<void> {
  const url = `${API_BASE}/snippets/${id}`;
  const res = await fetch(url, { method: "DELETE", credentials: "include" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`delete snippet failed (${res.status})`);
  }
}

export const apiServer = {
  listRFPs(token: string): Promise<RFP[]> {
    return serverFetch("/rfps", token);
  },

  getRFP(id: string, token: string): Promise<RFP> {
    return serverFetch(`/rfps/${id}`, token);
  },

  listRFPQuestions(rfpId: string, token: string): Promise<RFPQuestion[]> {
    return serverFetch(`/rfps/${rfpId}/questions`, token);
  },

  getLatestAnswer(
    rfpId: string,
    questionId: string,
    token: string
  ): Promise<RFPAnswer> {
    return serverFetch(
      `/rfps/${rfpId}/questions/${questionId}/answers/latest`,
      token
    );
  },

  listUsers(token: string): Promise<User[]> {
    return serverFetch("/users", token);
  },

  listDocuments(token: string): Promise<Document[]> {
    return serverFetch("/documents", token);
  },
};
