import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Routes that require authentication
const PROTECTED_PREFIXES = ["/rfps", "/ask", "/admin"];

// Routes that require specific roles
const ROLE_ROUTES: Record<string, string[]> = {
  "/admin/users": ["system_admin"],
  "/admin/documents": ["content_admin", "system_admin"],
};

interface JWTPayload {
  sub: string;
  role: string;
  exp: number;
}

/**
 * Decode a JWT without verifying the signature.
 * Signature verification happens on the API gateway; we only need the claims here.
 *
 * Uses atob (available in the Edge Runtime) instead of Buffer which is Node-only.
 */
function decodeJWT(token: string): JWTPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    // Base64url → base64 (pad and replace chars)
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const payload = JSON.parse(atob(padded)) as JWTPayload;
    return payload;
  } catch {
    return null;
  }
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );

  if (!isProtected) {
    return NextResponse.next();
  }

  const token = request.cookies.get("access_token")?.value;

  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  const payload = decodeJWT(token);

  // Check expiry
  if (!payload || payload.exp * 1000 < Date.now()) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    const response = NextResponse.redirect(loginUrl);
    response.cookies.delete("access_token");
    return response;
  }

  // Check role-based access
  for (const [route, allowedRoles] of Object.entries(ROLE_ROUTES)) {
    if (pathname === route || pathname.startsWith(`${route}/`)) {
      if (!allowedRoles.includes(payload.role)) {
        return NextResponse.redirect(new URL("/403", request.url));
      }
      break;
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all routes except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     * - /login (auth page)
     * - /403 (forbidden page)
     * - /api/* (API routes / rewrites)
     */
    "/((?!_next/static|_next/image|favicon.ico|login|403|api/).*)",
  ],
};
