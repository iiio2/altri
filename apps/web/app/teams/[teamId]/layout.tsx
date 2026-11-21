import { Suspense } from "react";

import { TeamShell } from "@/components/team/team-shell";

export default function TeamLayout({ children }: LayoutProps<"/teams/[teamId]">) {
  return (
    <Suspense>
      <TeamShell>{children}</TeamShell>
    </Suspense>
  );
}
