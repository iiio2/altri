"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { isApiError } from "@/lib/api/client";

function onAuthError(error: unknown) {
  // The session expired or was revoked: every screen needs a user, so go back to sign-in.
  if (isApiError(error, 401) && window.location.pathname !== "/login") {
    window.location.assign("/login");
  }
}

function makeQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache({ onError: onAuthError }),
    mutationCache: new MutationCache({ onError: onAuthError }),
    defaultOptions: {
      queries: {
        // Freshness comes from live `changed` pushes, not from polling.
        staleTime: 60_000,
        // 4xx answers (no access, unknown id) won't change on retry.
        retry: (count, error) => !(isApiError(error) && error.status < 500) && count < 2,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

function getQueryClient() {
  // Keep server renders isolated and reuse one client in the browser.
  if (typeof window === "undefined") return makeQueryClient();
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={getQueryClient()}>
      <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
    </QueryClientProvider>
  );
}
