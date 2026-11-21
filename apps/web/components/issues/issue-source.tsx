import { CircleSlashIcon, GaugeIcon, MountainIcon } from "lucide-react";

import type { IssueSource as Source } from "@/lib/api/types";
import { formatWeek } from "@/lib/format";

/** Where an Issue came from: a Scorecard cell, an off-track Rock or an overdue To-Do. */
export function IssueSource({ source }: { source: Source }) {
  switch (source.kind) {
    case "score":
      return (
        <span className="inline-flex items-center gap-1">
          <GaugeIcon className="size-3.5" aria-hidden="true" />
          <span>
            {source.measurable_name} · week of {formatWeek(source.week_start)}
          </span>
        </span>
      );
    case "rock":
      return (
        <span className="inline-flex items-center gap-1">
          <MountainIcon className="size-3.5" aria-hidden="true" />
          <span>Rock: {source.rock_title}</span>
        </span>
      );
    case "todo":
      return (
        <span className="inline-flex items-center gap-1">
          <CircleSlashIcon className="size-3.5" aria-hidden="true" />
          <span>Overdue To-Do: {source.todo_title}</span>
        </span>
      );
  }
}
