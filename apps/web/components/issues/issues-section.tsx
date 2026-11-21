"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ErrorState } from "@/components/common/error-state";
import { EmptyState, Section, SectionSkeleton } from "@/components/common/section";
import { useTeam } from "@/components/team/team-context";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { issuesQuery } from "@/lib/api/queries";
import type { Issue } from "@/lib/api/types";
import { formatInstant } from "@/lib/format";

import { AddTodoDialog } from "./add-todo-dialog";
import { IssueSource } from "./issue-source";
import { NewIssueForm } from "./new-issue-form";
import { PrioritySelect, PriorityTag } from "./priority-select";
import { SolveIssueDialog } from "./solve-issue-dialog";
import { useSetPriority } from "./use-issue-mutations";

type View = "open" | "solved";

/** Unsolved Issues in Issue order, with solved ones a tab away. Team page and the meeting's IDS section. */
export function IssuesSection({ anchor }: { anchor?: string }) {
  const { teamId, canWrite } = useTeam();
  const [view, setView] = useState<View>("open");
  const open = useQuery(issuesQuery(teamId, "open"));
  const solved = useQuery({ ...issuesQuery(teamId, "solved"), enabled: view === "solved" });
  const current = view === "open" ? open : solved;

  return (
    <Section
      anchor={anchor}
      title="Issues"
      description="Priority 5 first, then oldest first"
      actions={
        <Tabs value={view} onValueChange={(v) => setView(v as View)}>
          <TabsList>
            <TabsTrigger value="open">Open{open.data ? ` (${open.data.length})` : ""}</TabsTrigger>
            <TabsTrigger value="solved">Solved</TabsTrigger>
          </TabsList>
        </Tabs>
      }
    >
      {view === "open" && canWrite && <NewIssueForm teamId={teamId} />}
      {current.isPending ? (
        <SectionSkeleton />
      ) : current.isError ? (
        <div className="p-4">
          <ErrorState error={current.error} onRetry={() => current.refetch()} />
        </div>
      ) : current.data.length === 0 ? (
        <EmptyState>{view === "open" ? "No open Issues. Nice." : "No solved Issues yet."}</EmptyState>
      ) : view === "open" ? (
        <ol className="divide-y" aria-label="Open Issues in Issue order">
          {current.data.map((issue, index) => (
            <OpenIssueRow key={issue.id} issue={issue} rank={index + 1} />
          ))}
        </ol>
      ) : (
        <ul className="divide-y" aria-label="Solved Issues">
          {current.data.map((issue) => (
            <SolvedIssueRow key={issue.id} issue={issue} />
          ))}
        </ul>
      )}
    </Section>
  );
}

function OpenIssueRow({ issue, rank }: { issue: Issue; rank: number }) {
  const { teamId, team, canWrite } = useTeam();
  const setPriority = useSetPriority(teamId);

  return (
    <li className="flex flex-wrap items-start gap-x-3 gap-y-2 px-4 py-3">
      <span className="w-5 pt-1 text-right text-sm text-muted-foreground tabular-nums" aria-hidden="true">
        {rank}
      </span>
      {canWrite ? (
        <PrioritySelect
          value={issue.priority}
          onChange={(priority) => setPriority.mutate({ issue, priority })}
          label={`Priority for ${issue.title}`}
        />
      ) : (
        <PriorityTag value={issue.priority} />
      )}
      <div className="min-w-48 flex-1">
        <p className="text-sm font-medium">{issue.title}</p>
        <p className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
          <span>{issue.owner.name}</span>
          <span aria-hidden="true">·</span>
          <span>Opened {formatInstant(issue.created_at, team.timezone)}</span>
          {issue.source && (
            <>
              <span aria-hidden="true">·</span>
              <IssueSource source={issue.source} />
            </>
          )}
        </p>
      </div>
      {canWrite && (
        <div className="ml-auto flex items-center gap-1">
          <AddTodoDialog issue={issue} />
          <SolveIssueDialog teamId={teamId} issue={issue} />
        </div>
      )}
    </li>
  );
}

function SolvedIssueRow({ issue }: { issue: Issue }) {
  const { team } = useTeam();
  return (
    <li className="px-4 py-3">
      <p className="text-sm font-medium">{issue.title}</p>
      <p className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-muted-foreground">
        <span>{issue.owner.name}</span>
        <span aria-hidden="true">·</span>
        <span>Solved {issue.solved_at && formatInstant(issue.solved_at, team.timezone)}</span>
        {issue.source && (
          <>
            <span aria-hidden="true">·</span>
            <IssueSource source={issue.source} />
          </>
        )}
      </p>
      {issue.resolution_note && (
        <p className="mt-2 rounded-md bg-muted px-3 py-2 text-sm whitespace-pre-line">{issue.resolution_note}</p>
      )}
    </li>
  );
}
