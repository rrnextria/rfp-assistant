"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const NAV_LINKS = [
  {
    href: "/ask",
    label: "Ask AI",
    icon: "💬",
  },
  {
    href: "/rfps",
    label: "RFPs",
    icon: "📋",
  },
];

const ADMIN_LINKS = [
  { href: "/admin/documents", label: "Documents", icon: "📄" },
  { href: "/admin/users", label: "Users", icon: "👥" },
  { href: "/admin/companies", label: "Companies", icon: "🏢" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    router.push("/login");
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      {/* Top navigation bar */}
      <header className="sticky top-0 z-40 border-b bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          {/* Brand */}
          <Link href="/rfps" className="flex items-center gap-2">
            <span className="text-xl font-bold text-blue-700">RFP Assistant</span>
            <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-600">
              by Nextria
            </span>
          </Link>

          {/* Primary nav */}
          <nav className="flex items-center gap-1">
            {NAV_LINKS.map((link) => {
              const active =
                pathname === link.href || pathname.startsWith(link.href + "/");
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    active
                      ? "bg-blue-50 text-blue-700"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                  }`}
                >
                  <span>{link.icon}</span>
                  {link.label}
                </Link>
              );
            })}

            {/* Admin dropdown */}
            <div className="relative group">
              <button
                className={`flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  pathname.startsWith("/admin")
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                }`}
              >
                <span>⚙️</span>
                Admin
              </button>
              <div className="absolute right-0 top-full hidden group-hover:block z-50 w-44 rounded-lg border bg-white py-1 shadow-lg">
                {ADMIN_LINKS.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <span>{link.icon}</span>
                    {link.label}
                  </Link>
                ))}
              </div>
            </div>
          </nav>

          {/* Right: logout */}
          <button
            onClick={handleLogout}
            className="rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1">{children}</main>

      {/* Footer */}
      <footer className="border-t bg-white py-3">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4">
          <p className="text-xs text-gray-400" suppressHydrationWarning>
            Built:{" "}
            {process.env.NEXT_PUBLIC_BUILD_DATE
              ? process.env.NEXT_PUBLIC_BUILD_DATE.replace("T", " ").slice(0, 16) + " UTC"
              : "—"}
          </p>
          <p className="text-xs text-gray-400">
            Nextria RFP Assistant · AI-powered responses with citations
          </p>
        </div>
      </footer>
    </div>
  );
}
