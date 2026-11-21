"use client";

import { createContext, use } from "react";

import type { Me, TeamDetail } from "@/lib/api/types";
import type { LiveStatus } from "@/lib/live/use-team-live";

export type TeamContextValue = {
  teamId: string;
  team: TeamDetail;
  me: Me;
  /**
   * Admins and Team Members. Only decides which controls are shown; the API refuses Observer writes
   * regardless.
   */
  canWrite: boolean;
  live: LiveStatus;
};

export const TeamContext = createContext<TeamContextValue | null>(null);

/** The open team, the signed-in user and the live connection. Available under /teams/[teamId]. */
export function useTeam(): TeamContextValue {
  const value = use(TeamContext);
  if (!value) throw new Error("useTeam() must be used inside <TeamShell>");
  return value;
}
