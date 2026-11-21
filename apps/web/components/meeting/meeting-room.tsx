"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect } from "react";

import { ErrorState } from "@/components/common/error-state";
import { IssuesSection } from "@/components/issues/issues-section";
import { ScorecardSection } from "@/components/scorecard/scorecard-section";
import { useTeam } from "@/components/team/team-context";
import { TodosSection } from "@/components/todos/todos-section";
import { Skeleton } from "@/components/ui/skeleton";
import { meetingQuery } from "@/lib/api/queries";
import type { MeetingState } from "@/lib/api/types";

import { AttendeesPanel } from "./attendees-panel";
import { MeetingBar } from "./meeting-bar";
import { MeetingSummary } from "./meeting-summary";
import { RatingPanel } from "./rating-panel";
import { useJoinMeeting } from "./use-meeting-mutations";

/**
 * The Level 10 Meeting page. State comes from the cache, which the live socket keeps current, so every
 * browser shows the facilitator's section and the server's timer. Opening a running meeting joins it, and the
 * page turns into the summary for everyone the moment the meeting ends.
 */
export function MeetingRoom() {
  const { meetingId } = useParams<{ teamId: string; meetingId: string }>();
  const { teamId } = useTeam();
  const meeting = useQuery(meetingQuery(teamId, meetingId));

  if (meeting.isPending) {
    return (
      <div className="mx-auto w-full max-w-7xl space-y-4 px-4 py-6" aria-busy="true" aria-label="Loading meeting">
        <Skeleton className="h-14" />
        <Skeleton className="h-96" />
      </div>
    );
  }
  if (meeting.isError) {
    return (
      <div className="mx-auto w-full max-w-2xl px-4 py-12">
        <ErrorState error={meeting.error} title="Couldn't open this meeting" onRetry={() => meeting.refetch()} />
      </div>
    );
  }
  if (meeting.data.status === "ended") {
    return (
      <main className="mx-auto w-full max-w-5xl px-4 py-6">
        <MeetingSummary meetingId={meetingId} />
      </main>
    );
  }
  return <ActiveMeeting meeting={meeting.data} />;
}

function ActiveMeeting({ meeting }: { meeting: MeetingState }) {
  const { teamId, team, me } = useTeam();
  const join = useJoinMeeting(teamId, meeting.id);
  const attending = meeting.attendees.some((a) => a.id === me.user.id);
  const { mutate: joinMeeting, isIdle: notTriedJoining } = join;

  useEffect(() => {
    // Opening the meeting is joining it (anyone who can read the team may). Tried once per visit.
    if (!attending && notTriedJoining) joinMeeting();
  }, [attending, notTriedJoining, joinMeeting]);

  return (
    <>
      <MeetingBar meeting={meeting} />
      <main className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[1fr_16rem]">
        <div className="min-w-0 space-y-6">
          <h1 className="sr-only">
            Level 10 Meeting, {team.name}: {meeting.agenda.find((a) => a.section === meeting.section)?.label}
          </h1>
          {meeting.section === "scorecard" && <ScorecardSection reviewWeek={meeting.scorecard_week} />}
          {meeting.section === "ids" && <IssuesSection />}
          {meeting.section === "conclude" && (
            <div className="grid gap-6 xl:grid-cols-2">
              <TodosSection meetingId={meeting.id} title="New To-Dos" />
              <RatingPanel meeting={meeting} />
            </div>
          )}
        </div>
        <aside className="space-y-4">
          <AttendeesPanel meeting={meeting} />
        </aside>
      </main>
    </>
  );
}
