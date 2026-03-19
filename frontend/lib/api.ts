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
  created_at?: string;
}

export interface RFP {
  id: string;
  customer: string;
  industry: string;
  region: string;
  created_by?: string;
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
  }): Promise<RFP> {
    return apiFetch("/rfps", {
      method: "POST",
      body: JSON.stringify(payload),
    });
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
