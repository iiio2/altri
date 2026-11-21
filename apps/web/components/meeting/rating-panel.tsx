"use client";

import { Section } from "@/components/common/section";
import { useTeam } from "@/components/team/team-context";
import type { MeetingState } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { useRateMeeting } from "./use-meeting-mutations";

const SCALE = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;

/** Conclude: each attending Admin or Team Member rates 1–10 and can change it until the meeting ends. */
export function RatingPanel({ meeting }: { meeting: MeetingState }) {
  const { teamId, me } = useTeam();
  const rate = useRateMeeting(teamId, meeting.id);
  const ratings = new Map(meeting.ratings.map((r) => [r.user_id, r.rating]));
  const attending = meeting.attendees.some((a) => a.id === me.user.id);
  const canRate = me.can_write && attending;
  const mine = rate.isPending ? rate.variables : ratings.get(me.user.id);

  return (
    <Section
      title="Rate the meeting"
      description={
        meeting.average_rating === null ? (
          "No ratings yet"
        ) : (
          <span>
            Average <span className="font-semibold text-foreground tabular-nums">{meeting.average_rating.toFixed(1)}</span>{" "}
            from {meeting.ratings.length} {meeting.ratings.length === 1 ? "rating" : "ratings"}
          </span>
        )
      }
    >
      <div className="space-y-4 p-4">
        {canRate ? (
          <fieldset>
            <legend className="mb-2 text-sm font-medium">
              Your rating{" "}
              <span className="font-normal text-muted-foreground">(you can change it until the meeting ends)</span>
            </legend>
            {/* Native radios: arrow keys and screen readers work without extra code. */}
            <div className="flex flex-wrap gap-1.5">
              {SCALE.map((n) => (
                <label
                  key={n}
                  className={cn(
                    "flex size-9 cursor-pointer items-center justify-center rounded-md border text-sm font-medium tabular-nums hover:bg-muted has-focus-visible:ring-2 has-focus-visible:ring-ring",
                    mine === n && "border-primary bg-primary text-primary-foreground hover:bg-primary/90",
                  )}
                >
                  <input
                    type="radio"
                    name={`rating-${meeting.id}`}
                    value={n}
                    checked={mine === n}
                    onChange={() => rate.mutate(n)}
                    className="sr-only"
                  />
                  {n}
                </label>
              ))}
            </div>
          </fieldset>
        ) : (
          <p className="text-sm text-muted-foreground">
            {me.can_write ? "Join the meeting to rate it." : "Observers don't rate meetings."}
          </p>
        )}

        <ul className="divide-y rounded-md border" aria-label="Ratings">
          {meeting.attendees.map((a) => {
            const value = ratings.get(a.id);
            return (
              <li key={a.id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span>{a.name}</span>
                {a.role === "observer" ? (
                  <span className="text-xs text-muted-foreground">Observer</span>
                ) : value === undefined ? (
                  <span className="text-xs text-muted-foreground">Not rated yet</span>
                ) : (
                  <span className="font-semibold tabular-nums">{value}</span>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </Section>
  );
}
