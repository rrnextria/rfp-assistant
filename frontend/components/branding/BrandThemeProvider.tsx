"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { getTenant, type Tenant } from "@/lib/api";

interface BrandContextValue {
  tenant: Tenant | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const BrandContext = createContext<BrandContextValue>({
  tenant: null,
  loading: true,
  error: null,
  refresh: () => {},
});

/**
 * Wraps the app, fetches `/tenants/me` once, and pushes
 * `brand.primary_color` and `brand.accent_color` to CSS variables
 * so the rest of the UI can use `var(--brand-primary)` / `var(--brand-accent)`.
 * Anonymous routes (e.g. /login) get a 401 and just keep the defaults.
 */
export function BrandThemeProvider({ children }: { children: React.ReactNode }) {
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getTenant()
      .then((t) => {
        if (cancelled) return;
        setTenant(t);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // Anonymous (e.g. /login) — keep defaults silently.
        setError(err instanceof Error ? err.message : "tenant fetch failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    const brand = tenant?.brand ?? {};
    if (brand.primary_color) {
      root.style.setProperty("--brand-primary", brand.primary_color);
    }
    if (brand.accent_color) {
      root.style.setProperty("--brand-accent", brand.accent_color);
    }
  }, [tenant]);

  return (
    <BrandContext.Provider
      value={{
        tenant,
        loading,
        error,
        refresh: () => setTick((n) => n + 1),
      }}
    >
      {children}
    </BrandContext.Provider>
  );
}

export function useBrand() {
  return useContext(BrandContext);
}
