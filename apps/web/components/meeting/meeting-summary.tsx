"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";

import { ErrorState } from "@/components/common/error-state";
import { EmptyState, Section, SectionSkeleton } from "@/components/common/section";
import { StatusBadge } from "@/components/common/status-badge";
import { useTeam } from "@/components/team/team-context";
import { Button } from "@/components/ui/button";
import { summaryQuery } from "@/lib/api/queries";
import { formatDay, formatGoal, formatInstant, formatLength, formatWeek, roleLabel, withUnit } from "@/lib/format";

/** What attendees see when the meeting ends; also any past meeting's summary. */
export function MeetingSummary({ meetingId }: { meetingId: string }) {
  const { teamId, team } = useTeam();
  const summary = useQuery(summaryQuery(teamId, meetingId));

  if (summary.isPending) return <SectionSkeleton rows={8} />;
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;
  const s = summary.data;
  const ratings = new Map(s.ratings.map((r) => [r.user_id, r.rating]));
  const lengthSeconds = (Date.parse(s.ended_at) - Date.parse(s.started_at)) / 1000;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Meeting summary</p>
          <h1 className="text-2xl font-semibold tracking-tight">Level 10 Meeting · {team.name}</h1>
          <p className="text-sm text-muted-foreground">
            {formatInstant(s.started_at, team.timezone)} · {formatLength(lengthSeconds)} · facilitated by {s.facilitator.name}
          </p>
        </div>
        <div className="flex items-center gap-6">
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Rating</p>
            <p className="text-3xl font-semibold tabular-nums" data-testid="summary-rating">
              {s.average_rating === null ? "—" : s.average_rating.toFixed(1)}
            </p>
          </div>
          <Button asChild variant="outline">
            <Link href={`/teams/${teamId}`}>
              <ArrowLeftIcon />
              Back to team
            </Link>
          </Button>
        </div>
      </div>

      <Section title="Scorecard" description={`Week of ${formatWeek(s.scorecard_week)}`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b">
                <th scope="col" className="px-4 py-2 text-left font-medium">Measurable</th>
                <th scope="col" className="px-4 py-2 text-left font-medium">Owner</th>
                <th scope="col" className="px-4 py-2 text-left font-medium">Goal</th>
                <th scope="col" className="px-4 py-2 text-right font-medium">Score</th>
                <th scope="col" className="px-4 py-2 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {s.measurables.map((m) => (
                <tr key={m.id}>
                  <th scope="row" className="px-4 py-2 text-left font-medium">{m.name}</th>
                  <td className="px-4 py-2 text-muted-foreground">{m.owner.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{formatGoal(m.goal, m.unit)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{m.value === null ? "—" : withUnit(m.value, m.unit)}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={m.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Issues solved" description={`${s.issues_solved.length} in this meeting`}>
          {s.issues_solved.length === 0 ? (
            <EmptyState>No Issues were solved.</EmptyState>
          ) : (
            <ul className="divide-y">
              {s.issues_solved.map((i) => (
                <li key={i.id} className="px-4 py-3">
                  <p className="text-sm font-medium">{i.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {i.owner.name} · solved {formatInstant(i.solved_at, team.timezone)}
                  </p>
                  <p className="mt-1.5 rounded-md bg-muted px-3 py-2 text-sm whitespace-pre-line">{i.resolution_note}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="To-Dos created" description={`${s.todos_created.length} in this meeting`}>
          {s.todos_created.length === 0 ? (
            <EmptyState>No To-Dos were created.</EmptyState>
          ) : (
            <ul className="divide-y">
              {s.todos_created.map((t) => (
                <li key={t.id} className="flex items-baseline justify-between gap-3 px-4 py-2.5">
                  <span className="text-sm font-medium">{t.title}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {t.owner.name} · due {formatDay(t.due_date)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section title="Attendees" description={`${s.attendees.length} attended`}>
        <ul className="divide-y">
          {s.attendees.map((a) => (
            <li key={a.id} className="flex items-center justify-between px-4 py-2 text-sm">
              <span>
                {a.name} <span className="text-xs text-muted-foreground">· {roleLabel[a.role]}</span>
              </span>
              <span className="tabular-nums">
                {ratings.has(a.id) ? (
                  <span className="font-semibold">{ratings.get(a.id)}</span>
                ) : (
                  <span className="text-xs text-muted-foreground">No rating</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
