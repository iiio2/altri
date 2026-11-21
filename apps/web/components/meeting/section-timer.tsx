"use client";

import { TimerIcon, TimerOffIcon } from "lucide-react";

import type { MeetingState } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { useSectionClock } from "@/lib/live/use-section-clock";
import { cn } from "@/lib/utils";

/**
 * Time left in the current section, counting down from its time box. Past it, the section shows as over time
 * (counting up) and does not advance on its own; only the facilitator moves on.
 */
export function SectionTimer({ meeting, size = "lg" }: { meeting: MeetingState; size?: "sm" | "lg" }) {
  const clock = useSectionClock(meeting);
  if (!clock) return null;
  const { remaining, duration, overTime } = clock;
  const Icon = overTime ? TimerOffIcon : TimerIcon;

  return (
    <div
      className={cn("flex items-center gap-2", overTime ? "text-destructive" : "text-foreground")}
      data-testid="section-timer"
      data-over-time={overTime}
    >
      <Icon className={size === "lg" ? "size-5" : "size-4"} aria-hidden="true" />
      <div role="timer" aria-label={overTime ? "Over time" : "Time left in this section"}>
        <span className={cn("font-semibold tabular-nums", size === "lg" ? "text-2xl" : "text-sm")}>
          {overTime ? `+${formatDuration(-remaining)}` : formatDuration(remaining)}
        </span>
        <span className={cn("ml-1.5 text-xs", overTime ? "font-medium" : "text-muted-foreground")}>
          {overTime ? "over time" : `left of ${formatDuration(duration)}`}
        </span>
      </div>
      {/* Announced once when the section runs over, not on every tick. */}
      <output className="sr-only">{overTime ? "This section is over time." : ""}</output>
    </div>
  );
}
