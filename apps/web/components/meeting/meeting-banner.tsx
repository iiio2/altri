"use client";

import { useQuery } from "@tanstack/react-query";
import { PlayIcon, UsersRoundIcon } from "lucide-react";
import Link from "next/link";

import { useTeam } from "@/components/team/team-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { activeMeetingQuery } from "@/lib/api/queries";

import { SectionTimer } from "./section-timer";
import { useStartMeeting } from "./use-meeting-mutations";

/** Team page call to action: join the running Level 10 Meeting, or start one. Updates live. */
export function MeetingBanner() {
  const { teamId, canWrite } = useTeam();
  const active = useQuery(activeMeetingQuery(teamId));
  const start = useStartMeeting(teamId);

  if (active.isPending) return <Skeleton className="h-16" />;
  const meeting = active.data;

  if (meeting) {
    const section = meeting.agenda.find((a) => a.section === meeting.section)?.label ?? meeting.section;
    return (
      <section
        className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg border border-primary/20 bg-primary/5 px-4 py-3"
        aria-label="Meeting in progress"
      >
        <div className="flex items-center gap-3">
          <span className="relative flex size-2.5" aria-hidden="true">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
            <span className="relative inline-flex size-2.5 rounded-full bg-success" />
          </span>
          <div>
            <p className="text-sm font-semibold">Level 10 Meeting in progress</p>
            <p className="text-xs text-muted-foreground">
              {section} · facilitated by {meeting.facilitator.name} · {meeting.attendees.length} attending
            </p>
          </div>
        </div>
        <SectionTimer meeting={meeting} size="sm" />
        <Button asChild className="ml-auto">
          <Link href={`/teams/${teamId}/meetings/${meeting.id}`}>
            <UsersRoundIcon />
            Join meeting
          </Link>
        </Button>
      </section>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg border px-4 py-3">
      <div>
        <p className="text-sm font-semibold">Level 10 Meeting</p>
        <p className="text-xs text-muted-foreground">
          Scorecard 5 min · IDS 60 min · Conclude 10 min.{" "}
          {canWrite ? "Starting it makes you the facilitator." : "You can join once a teammate starts it."}
        </p>
      </div>
      {canWrite && (
        <Button className="ml-auto" onClick={() => start.mutate()} disabled={start.isPending}>
          <PlayIcon />
          {start.isPending ? "Starting…" : "Start meeting"}
        </Button>
      )}
    </div>
  );
}
