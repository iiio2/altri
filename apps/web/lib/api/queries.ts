import { queryOptions, type QueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { MeetingState } from "./types";
import type { components } from "./schema";

/**
 * Query keys. Everything team-scoped lives under ["team", teamId, <resource>, ...], where <resource> is one
 * of the names the live socket sends in `changed` events, so a push invalidates exactly that subtree.
 */
export const keys = {
  me: ["me"] as const,
  users: ["users"] as const,
  team: (teamId: string) => ["team", teamId] as const,
  teamDetail: (teamId: string) => ["team", teamId, "detail"] as const,
  scorecard: (teamId: string) => ["team", teamId, "scorecard"] as const,
  issues: (teamId: string, status: "open" | "solved") => ["team", teamId, "issues", status] as const,
  todos: (teamId: string, meetingId?: string) => ["team", teamId, "todos", meetingId ?? "all"] as const,
  rocks: (teamId: string) => ["team", teamId, "rocks"] as const,
  activeMeeting: (teamId: string) => ["team", teamId, "meeting", "active"] as const,
  meeting: (teamId: string, meetingId: string) => ["team", teamId, "meeting", meetingId] as const,
  summary: (teamId: string, meetingId: string) => ["team", teamId, "meeting", meetingId, "summary"] as const,
};

/** Resources the API names in live `changed` events (apps/api/src/altri_api/live/hub.py `Resource`). */
export type LiveResource = "scorecard" | "issues" | "todos" | "rocks" | "meeting";

export function invalidateResource(qc: QueryClient, teamId: string, resource: LiveResource) {
  if (resource === "meeting") {
    // Meeting *state* arrives by push; `meeting` here means meeting-scoped lists (summary) changed.
    return qc.invalidateQueries({
      queryKey: [...keys.team(teamId), "meeting"],
      predicate: (q) => q.queryKey.at(-1) === "summary",
    });
  }
  return qc.invalidateQueries({ queryKey: [...keys.team(teamId), resource] });
}

const p = (team_id: string) => ({ params: { path: { team_id } } });

export const meQuery = queryOptions({
  queryKey: keys.me,
  queryFn: () => unwrap(api.GET("/api/v1/auth/me")),
});

export const usersQuery = queryOptions({
  queryKey: keys.users,
  queryFn: () => unwrap(api.GET("/api/v1/auth/users")),
  staleTime: Infinity,
});

export const teamQuery = (teamId: string) =>
  queryOptions({
    queryKey: keys.teamDetail(teamId),
    queryFn: () => unwrap(api.GET("/api/v1/teams/{team_id}", p(teamId))),
  });

export const scorecardQuery = (teamId: string) =>
  queryOptions({
    queryKey: keys.scorecard(teamId),
    queryFn: () => unwrap(api.GET("/api/v1/teams/{team_id}/scorecard", p(teamId))),
  });

export const issuesQuery = (teamId: string, status: "open" | "solved") =>
  queryOptions({
    queryKey: keys.issues(teamId, status),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/teams/{team_id}/issues", { params: { path: { team_id: teamId }, query: { status } } }),
      ),
  });

export const todosQuery = (teamId: string, meetingId?: string) =>
  queryOptions({
    queryKey: keys.todos(teamId, meetingId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/teams/{team_id}/todos", {
          params: { path: { team_id: teamId }, query: meetingId ? { meeting_id: meetingId } : {} },
        }),
      ),
  });

export const rocksQuery = (teamId: string) =>
  queryOptions({
    queryKey: keys.rocks(teamId),
    queryFn: () => unwrap(api.GET("/api/v1/teams/{team_id}/rocks", p(teamId))),
  });

// --- Meeting state ------------------------------------------------------------------------------------

type RawMeetingState = components["schemas"]["MeetingStateOut"];

export function stampMeeting(raw: RawMeetingState): MeetingState {
  return { ...raw, received_at: performance.now() };
}

/**
 * REST responses and socket pushes can arrive out of order. For the same meeting, keep whichever snapshot the
 * server built later, so a slow response can never roll the agenda back.
 */
export function newerMeeting<T extends MeetingState | null | undefined>(prev: T | undefined, next: T): T {
  if (prev && next && prev.id === next.id && Date.parse(prev.server_now) > Date.parse(next.server_now)) {
    return prev;
  }
  return next;
}

export const activeMeetingQuery = (teamId: string) =>
  queryOptions({
    queryKey: keys.activeMeeting(teamId),
    queryFn: async () => {
      const raw = await unwrap(api.GET("/api/v1/teams/{team_id}/meetings/active", p(teamId)));
      return raw ? stampMeeting(raw) : null;
    },
    structuralSharing: (prev, next) => newerMeeting(prev as MeetingState | null, next as MeetingState | null),
  });

export const meetingQuery = (teamId: string, meetingId: string) =>
  queryOptions({
    queryKey: keys.meeting(teamId, meetingId),
    queryFn: async () =>
      stampMeeting(
        await unwrap(
          api.GET("/api/v1/teams/{team_id}/meetings/{meeting_id}", {
            params: { path: { team_id: teamId, meeting_id: meetingId } },
          }),
        ),
      ),
    structuralSharing: (prev, next) => newerMeeting(prev as MeetingState, next as MeetingState),
  });

export const summaryQuery = (teamId: string, meetingId: string) =>
  queryOptions({
    queryKey: keys.summary(teamId, meetingId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/teams/{team_id}/meetings/{meeting_id}/summary", {
          params: { path: { team_id: teamId, meeting_id: meetingId } },
        }),
      ),
  });

/** Put a meeting snapshot (from a push or a mutation response) into every cache entry that shows it. */
export function applyMeetingState(qc: QueryClient, raw: RawMeetingState) {
  const state = stampMeeting(raw);
  const teamId = state.team_id;
  qc.setQueryData<MeetingState>(keys.meeting(teamId, state.id), (prev) => newerMeeting(prev, state));
  qc.setQueryData<MeetingState | null>(keys.activeMeeting(teamId), (prev) => {
    if (state.status === "active") return newerMeeting(prev, state);
    return prev?.id === state.id ? null : prev;
  });
  if (state.status === "ended") {
    // Everything solved / created during the meeting is final now.
    void qc.invalidateQueries({ queryKey: keys.summary(teamId, state.id) });
  }
}
