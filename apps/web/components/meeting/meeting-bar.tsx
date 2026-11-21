"use client";

import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, SquareIcon } from "lucide-react";
import { useState } from "react";

import { useTeam } from "@/components/team/team-context";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { MeetingState } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

import { SectionTimer } from "./section-timer";
import { useEndMeeting, useSetSection } from "./use-meeting-mutations";

/**
 * Agenda, timer and (for the facilitator) the controls. Sticky under the app header so the time box and the
 * current section are always in view.
 */
export function MeetingBar({ meeting }: { meeting: MeetingState }) {
  const { teamId, me } = useTeam();
  const isFacilitator = meeting.facilitator.id === me.user.id;
  const setSection = useSetSection(teamId, meeting.id);
  const index = meeting.agenda.findIndex((a) => a.section === meeting.section);
  const prev = meeting.agenda[index - 1];
  const next = meeting.agenda[index + 1];

  return (
    <div className="sticky top-14 z-20 border-b bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/85">
      <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <nav aria-label="Agenda">
          <ol className="flex items-center gap-1">
            {meeting.agenda.map((item, i) => {
              const state = i < index ? "done" : i === index ? "current" : "upcoming";
              const content = (
                <>
                  <span
                    className={cn(
                      "flex size-5 items-center justify-center rounded-full text-[0.7rem] font-semibold",
                      state === "current" && "bg-primary text-primary-foreground",
                      state === "done" && "bg-muted text-muted-foreground",
                      state === "upcoming" && "border text-muted-foreground",
                    )}
                    aria-hidden="true"
                  >
                    {state === "done" ? <CheckIcon className="size-3" /> : i + 1}
                  </span>
                  <span className={cn("text-sm", state === "current" ? "font-semibold" : "text-muted-foreground")}>
                    {item.label}
                  </span>
                  <span className="text-xs text-muted-foreground">{formatDuration(item.duration_seconds)}</span>
                </>
              );
              const classes = cn(
                "flex items-center gap-1.5 rounded-md px-2 py-1",
                state === "current" && "bg-accent",
              );
              return (
                <li key={item.section} aria-current={state === "current" ? "step" : undefined}>
                  {isFacilitator && state !== "current" ? (
                    <button
                      type="button"
                      className={cn(classes, "outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring")}
                      onClick={() => setSection.mutate(item.section)}
                      disabled={setSection.isPending}
                      aria-label={`Go to ${item.label}`}
                    >
                      {content}
                    </button>
                  ) : (
                    <span className={classes}>{content}</span>
                  )}
                </li>
              );
            })}
          </ol>
        </nav>

        <SectionTimer meeting={meeting} />

        <div className="ml-auto flex items-center gap-2">
          {isFacilitator ? (
            <>
              {prev && (
                <Button variant="outline" onClick={() => setSection.mutate(prev.section)} disabled={setSection.isPending}>
                  <ArrowLeftIcon />
                  {prev.label}
                </Button>
              )}
              {next ? (
                <Button onClick={() => setSection.mutate(next.section)} disabled={setSection.isPending}>
                  Next: {next.label}
                  <ArrowRightIcon />
                </Button>
              ) : null}
              <EndMeetingButton meetingId={meeting.id} primary={!next} />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Facilitated by <span className="font-medium text-foreground">{meeting.facilitator.name}</span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function EndMeetingButton({ meetingId, primary }: { meetingId: string; primary: boolean }) {
  const { teamId } = useTeam();
  const [open, setOpen] = useState(false);
  const end = useEndMeeting(teamId, meetingId);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={primary ? "default" : "outline"}>
          <SquareIcon />
          End meeting
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>End the meeting?</DialogTitle>
          <DialogDescription>
            Everyone moves to the summary and ratings close. This can&apos;t be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Keep going</Button>
          </DialogClose>
          <Button onClick={() => end.mutate(undefined, { onSuccess: () => setOpen(false) })} disabled={end.isPending}>
            {end.isPending ? "Ending…" : "End meeting"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
