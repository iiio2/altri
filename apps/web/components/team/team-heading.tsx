"use client";

import { EyeIcon } from "lucide-react";

import { formatDayLong } from "@/lib/format";

import { useTeam } from "./team-context";

const JUMP_LINKS = [
  { href: "#scorecard", label: "Scorecard" },
  { href: "#issues", label: "Issues" },
  { href: "#todos", label: "To-Dos" },
  { href: "#rocks", label: "Rocks" },
];

export function TeamHeading() {
  const { team, canWrite } = useTeam();
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{team.name}</h1>
        <p className="text-sm text-muted-foreground">
          Today is {formatDayLong(team.today)} · {team.current_quarter.replace("-", " ")}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        {!canWrite && (
          <span className="inline-flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
            <EyeIcon className="size-3.5" aria-hidden="true" />
            Read-only (Observer)
          </span>
        )}
        <nav aria-label="Sections" className="flex gap-1 text-sm">
          {JUMP_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-md px-2 py-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              {link.label}
            </a>
          ))}
        </nav>
      </div>
    </div>
  );
}
