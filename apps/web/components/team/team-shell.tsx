"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { ErrorState } from "@/components/common/error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { meQuery, teamQuery } from "@/lib/api/queries";
import { useTeamLive } from "@/lib/live/use-team-live";

import { AppHeader } from "./app-header";
import { TeamContext } from "./team-context";

/**
 * Loads the user and the team once for every page under /teams/[teamId], and holds the team's live
 * connection, so moving between the team page and the meeting page keeps one socket open.
 */
export function TeamShell({ children }: { children: ReactNode }) {
  const { teamId } = useParams<{ teamId: string }>();
  const me = useQuery(meQuery);
  const team = useQuery(teamQuery(teamId));
  const live = useTeamLive(teamId, team.isSuccess);

  let body: ReactNode;
  if (team.isError || me.isError) {
    body = (
      <div className="mx-auto w-full max-w-2xl space-y-4 px-4 py-12">
        <ErrorState
          error={team.error ?? me.error}
          title={team.error ? "You can't open this team" : undefined}
          onRetry={() => void Promise.all([me.refetch(), team.refetch()])}
        />
        <Button asChild variant="outline">
          <Link href="/">Go to your teams</Link>
        </Button>
      </div>
    );
  } else if (!me.data || !team.data) {
    body = (
      <div className="mx-auto w-full max-w-7xl space-y-4 px-4 py-6" aria-busy="true" aria-label="Loading team">
        <Skeleton className="h-12" />
        <Skeleton className="h-64" />
        <Skeleton className="h-48" />
      </div>
    );
  } else {
    body = (
      <TeamContext
        value={{ teamId, team: team.data, me: me.data, canWrite: me.data.can_write, live }}
      >
        {children}
      </TeamContext>
    );
  }

  return (
    <>
      <AppHeader teamId={teamId} me={me.data} teamName={team.data?.name} live={team.isSuccess ? live : null} />
      <div className="flex flex-1 flex-col">{body}</div>
    </>
  );
}
