"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { ErrorState } from "@/components/common/error-state";
import { EmptyState, Section, SectionSkeleton } from "@/components/common/section";
import { StatusBadge } from "@/components/common/status-badge";
import { useTeam } from "@/components/team/team-context";
import { scorecardQuery } from "@/lib/api/queries";
import { describeGoal, formatDay, formatGoal, formatWeek } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ScoreCell } from "./score-cell";

/**
 * Measurables by week for the last 13 weeks, current week last. Used on the team page and in the meeting's
 * Scorecard section, where `reviewWeek` is the week the meeting reviews.
 */
export function ScorecardSection({ reviewWeek, anchor }: { reviewWeek?: string; anchor?: string }) {
  const { teamId, canWrite } = useTeam();
  const scorecard = useQuery(scorecardQuery(teamId));
  const scroller = useRef<HTMLDivElement>(null);
  const loaded = scorecard.isSuccess;

  useEffect(() => {
    // Recent weeks are on the right; start scrolled there on narrow screens.
    if (loaded && scroller.current) scroller.current.scrollLeft = scroller.current.scrollWidth;
  }, [loaded]);

  const data = scorecard.data;
  const focusWeek = reviewWeek ?? data?.last_closed_week;

  return (
    <Section
      anchor={anchor}
      title="Scorecard"
      description={
        data && focusWeek
          ? `${reviewWeek ? "Reviewing" : "Last closed week"}: ${formatWeek(focusWeek)}`
          : "Weekly Measurables"
      }
      actions={
        <div className="flex items-center gap-1.5" aria-label="Legend">
          <StatusBadge status="on_track" />
          <StatusBadge status="off_track" />
          <StatusBadge status="pending" />
        </div>
      }
    >
      {scorecard.isPending ? (
        <SectionSkeleton rows={5} />
      ) : scorecard.isError ? (
        <div className="p-4">
          <ErrorState error={scorecard.error} onRetry={() => scorecard.refetch()} />
        </div>
      ) : data!.measurables.length === 0 ? (
        <EmptyState>This team has no Measurables.</EmptyState>
      ) : (
        <div ref={scroller} className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0 text-sm">
            <caption className="sr-only">
              Scorecard: Measurables by week. Week columns run oldest to newest; the last is the current week.
            </caption>
            <thead>
              <tr className="text-xs text-muted-foreground">
                <th
                  scope="col"
                  className="sticky left-0 z-10 min-w-56 border-b bg-card px-4 py-2 text-left font-medium"
                >
                  Measurable
                </th>
                {data!.weeks.map((week) => {
                  const isFocus = week === focusWeek;
                  const isCurrent = week === data!.current_week;
                  return (
                    <th
                      key={week}
                      scope="col"
                      aria-label={`Week of ${formatWeek(week)}${isCurrent ? " (current week)" : ""}${
                        isFocus ? " (under review)" : ""
                      }`}
                      className={cn(
                        "min-w-18 border-b px-1 py-2 text-right font-medium whitespace-nowrap",
                        isFocus && "bg-accent text-foreground",
                      )}
                    >
                      <span className="block">{formatDay(week)}</span>
                      <span className="block text-[0.7rem] font-normal">
                        {isCurrent ? "This week" : isFocus ? "Review" : " "}
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {data!.measurables.map((row) => (
                <tr key={row.id}>
                  <th scope="row" className="sticky left-0 z-10 border-b bg-card px-4 py-1.5 text-left font-normal">
                    <span className="block font-medium">{row.name}</span>
                    <span className="block text-xs text-muted-foreground">
                      {row.owner.name} · <span title={describeGoal(row.goal, row.unit)}>{formatGoal(row.goal, row.unit)}</span>
                    </span>
                  </th>
                  {row.cells.map((cell) => {
                    const isFocus = cell.week_start === focusWeek;
                    return (
                      <td key={cell.week_start} className={cn("border-b px-1 py-1", isFocus && "bg-accent")}>
                        <ScoreCell
                          teamId={teamId}
                          row={row}
                          cell={cell}
                          canWrite={canWrite}
                          emphasize={isFocus}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
