import { NextRequest, NextResponse } from "next/server";

const API_GATEWAY = process.env.NEXT_PUBLIC_API_URL ?? "http://api-gateway:8000";

export async function POST(request: NextRequest) {
  const body = await request.json();

  const upstream = await fetch(`${API_GATEWAY}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!upstream.ok) {
    const data = await upstream.json().catch(() => ({ detail: "Login failed" }));
    return NextResponse.json(data, { status: upstream.status });
  }

  const data = (await upstream.json()) as { access_token: string };

  const response = NextResponse.json({ ok: true });
  response.cookies.set("access_token", data.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8, // 8 hours
  });

  return response;
}
