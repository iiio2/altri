"use client";

import { useId, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * A titled page section. Team page and meeting page sections share this frame.
 *
 * `anchor` is the element id for in-page links; pass it only where links point (the team page). With Cache
 * Components, a page you navigated away from stays mounted but hidden, so the same section can be in the DOM
 * twice: fixed ids would collide, which is why the heading id comes from useId().
 */
export function Section({
  anchor,
  title,
  description,
  actions,
  children,
  className,
}: {
  anchor?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const headingId = useId();
  return (
    <section id={anchor} aria-labelledby={headingId} className={cn("scroll-mt-28 rounded-lg border bg-card", className)}>
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b px-4 py-3">
        <div className="min-w-0">
          <h2 id={headingId} className="text-base font-semibold tracking-tight">
            {title}
          </h2>
          {description && <div className="text-sm text-muted-foreground">{description}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </header>
      <div>{children}</div>
    </section>
  );
}

export function SectionSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9" />
      ))}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="px-4 py-8 text-center text-sm text-muted-foreground">{children}</p>;
}
