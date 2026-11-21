"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { api, isApiError, unwrap } from "@/lib/api/client";
import { applyMeetingState, keys } from "@/lib/api/queries";
import type { MeetingSection } from "@/lib/api/types";

const path = (teamId: string, meetingId: string) => ({ params: { path: { team_id: teamId, meeting_id: meetingId } } });

/** Start the Level 10 Meeting and open it. If one is already running, open that one instead. */
export function useStartMeeting(teamId: string) {
  const qc = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/teams/{team_id}/meetings", { params: { path: { team_id: teamId } } })),
    onSuccess: (state) => {
      applyMeetingState(qc, state);
      router.push(`/teams/${teamId}/meetings/${state.id}`);
    },
    onError: (error) => {
      const running =
        isApiError(error, 409) && typeof error.detail === "object" && error.detail && "meeting_id" in error.detail
          ? String(error.detail.meeting_id)
          : null;
      if (running) {
        toast.info("A meeting is already running", { description: "Joining it instead." });
        router.push(`/teams/${teamId}/meetings/${running}`);
      } else {
        toast.error("Meeting not started", { description: error.message });
      }
    },
  });
}

export function useJoinMeeting(teamId: string, meetingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/teams/{team_id}/meetings/{meeting_id}/join", path(teamId, meetingId))),
    onSuccess: (state) => applyMeetingState(qc, state),
    onError: (error) => toast.error("Couldn't join the meeting", { description: error.message }),
  });
}

/** Facilitator only. Names the target section, so a double click can't skip one. */
export function useSetSection(teamId: string, meetingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (section: MeetingSection) =>
      unwrap(
        api.PUT("/api/v1/teams/{team_id}/meetings/{meeting_id}/section", {
          ...path(teamId, meetingId),
          body: { section },
        }),
      ),
    onSuccess: (state) => applyMeetingState(qc, state),
    onError: (error) => toast.error("Couldn't change section", { description: error.message }),
  });
}

export function useRateMeeting(teamId: string, meetingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rating: number) =>
      unwrap(
        api.PUT("/api/v1/teams/{team_id}/meetings/{meeting_id}/rating", {
          ...path(teamId, meetingId),
          body: { rating },
        }),
      ),
    onSuccess: (state) => applyMeetingState(qc, state),
    onError: (error) => toast.error("Rating not saved", { description: error.message }),
  });
}

/** Facilitator only, at any time. Everyone's page switches to the summary when the ended state arrives. */
export function useEndMeeting(teamId: string, meetingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/teams/{team_id}/meetings/{meeting_id}/end", path(teamId, meetingId))),
    onSuccess: (summary) => {
      qc.setQueryData(keys.summary(teamId, meetingId), summary);
      // The ended state is pushed over the socket too; fetch it so this tab doesn't depend on that.
      return qc.invalidateQueries({ queryKey: keys.meeting(teamId, meetingId), exact: true });
    },
    onError: (error) => toast.error("Meeting not ended", { description: error.message }),
  });
}
