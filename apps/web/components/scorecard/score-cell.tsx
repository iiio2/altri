"use client";

import { CircleDotIcon, Loader2Icon, MessageSquarePlusIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { statusLabel } from "@/components/common/status-badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Cell, MeasurableRow } from "@/lib/api/types";
import { formatNumber, formatWeek } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useMakeIssueFromScore, useSetScore } from "./use-scorecard-mutations";

const TONE: Record<Cell["status"], string> = {
  on_track: "bg-success-muted text-success",
  off_track: "bg-destructive-muted text-destructive",
  pending: "text-muted-foreground",
};

function parseScore(draft: string): number | null | "invalid" {
  const text = draft.trim().replace(/,/g, "");
  if (text === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : "invalid";
}

/**
 * One week's score for one Measurable. Click (or Enter) to edit in place; Enter or leaving the field saves,
 * Escape cancels, and an empty field clears the score. Off-track cells offer Make it an Issue.
 */
export function ScoreCell({
  teamId,
  row,
  cell,
  canWrite,
  emphasize,
}: {
  teamId: string;
  row: MeasurableRow;
  cell: Cell;
  canWrite: boolean;
  /** The week under review: its Make it an Issue control is always visible. */
  emphasize: boolean;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const setScore = useSetScore(teamId);
  const makeIssue = useMakeIssueFromScore(teamId);
  const ref = { measurableId: row.id, week: cell.week_start };
  const display = cell.value === null ? "—" : formatNumber(cell.value);
  const label = `${row.name}, week of ${formatWeek(cell.week_start)}: ${
    cell.value === null ? "no score" : display
  }, ${statusLabel(cell.status)}`;

  const commit = () => {
    if (draft === null) return;
    const value = parseScore(draft);
    if (value === "invalid") {
      toast.error("Enter a number", { description: `"${draft}" isn't a number.` });
      return;
    }
    setDraft(null);
    if (value !== cell.value) setScore.mutate({ ...ref, value });
  };

  if (draft !== null) {
    return (
      <input
        autoFocus
        aria-label={`Score for ${row.name}, week of ${formatWeek(cell.week_start)}`}
        inputMode="decimal"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onFocus={(e) => e.target.select()}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") setDraft(null);
        }}
        className="h-9 w-full rounded-md border border-ring bg-background px-1.5 text-right text-sm tabular-nums outline-none ring-2 ring-ring/40"
      />
    );
  }

  const showIssueControl = cell.open_issue_id !== null || (canWrite && cell.status === "off_track");

  return (
    <div className="group/cell relative">
      {canWrite ? (
        <button
          type="button"
          aria-label={`${label}. Edit`}
          onClick={() => setDraft(cell.value === null ? "" : String(cell.value))}
          className={cn(
            "flex h-9 w-full items-center justify-end rounded-md px-1.5 text-sm tabular-nums outline-none hover:ring-1 hover:ring-border focus-visible:ring-2 focus-visible:ring-ring",
            TONE[cell.status],
            setScore.isPending && "opacity-60",
          )}
        >
          {display}
        </button>
      ) : (
        <div
          aria-label={label}
          className={cn("flex h-9 items-center justify-end rounded-md px-1.5 text-sm tabular-nums", TONE[cell.status])}
        >
          {display}
        </div>
      )}
      {showIssueControl && (
        <Tooltip>
          <TooltipTrigger asChild>
            {cell.open_issue_id !== null ? (
              <span className="absolute top-0.5 left-0.5 text-destructive">
                <CircleDotIcon className="size-3" aria-hidden="true" />
                <span className="sr-only">Has an open Issue</span>
              </span>
            ) : (
              <button
                type="button"
                aria-label={`Make it an Issue: ${row.name}, week of ${formatWeek(cell.week_start)}`}
                disabled={makeIssue.isPending}
                onClick={() => makeIssue.mutate(ref)}
                className={cn(
                  "absolute top-0.5 left-0.5 rounded-sm bg-background/90 p-0.5 text-destructive shadow-xs outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring",
                  emphasize ? "opacity-100" : "opacity-0 group-hover/cell:opacity-100",
                )}
              >
                {makeIssue.isPending ? (
                  <Loader2Icon className="size-3.5 animate-spin" />
                ) : (
                  <MessageSquarePlusIcon className="size-3.5" />
                )}
              </button>
            )}
          </TooltipTrigger>
          <TooltipContent>{cell.open_issue_id !== null ? "On the Issues list" : "Make it an Issue"}</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}
