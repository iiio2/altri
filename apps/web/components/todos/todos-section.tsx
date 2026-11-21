"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlertIcon, CircleCheckIcon, CircleIcon, MessageSquarePlusIcon, TargetIcon } from "lucide-react";
import { useId, useState } from "react";

import { ErrorState } from "@/components/common/error-state";
import { EmptyState, Section, SectionSkeleton } from "@/components/common/section";
import { useTeam } from "@/components/team/team-context";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { todosQuery } from "@/lib/api/queries";
import type { Completion, Todo } from "@/lib/api/types";
import { formatDay, formatInstant, formatWeek } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useMakeIssueFromTodo, useToggleTodo } from "./use-todo-mutations";

type Filter = "all" | "open" | "done";

/**
 * To-Dos ordered by due date, with overdue ones flagged and last closed week's completion rate. With
 * `meetingId`, only the To-Dos created during that meeting (the Conclude recap).
 */
export function TodosSection({
  meetingId,
  title = "To-Dos",
  anchor,
}: {
  meetingId?: string;
  title?: string;
  anchor?: string;
}) {
  const { teamId } = useTeam();
  const [filter, setFilter] = useState<Filter>("all");
  const todos = useQuery(todosQuery(teamId, meetingId));
  const shown = todos.data?.todos.filter((t) =>
    filter === "all" ? true : filter === "done" ? t.done_at !== null : t.done_at === null,
  );

  return (
    <Section
      anchor={anchor}
      title={title}
      description={
        meetingId ? "Created during this meeting" : todos.data && <CompletionSummary completion={todos.data.last_closed_week} />
      }
      actions={
        !meetingId && (
          <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
            <TabsList>
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="open">Open</TabsTrigger>
              <TabsTrigger value="done">Done</TabsTrigger>
            </TabsList>
          </Tabs>
        )
      }
    >
      {todos.isPending ? (
        <SectionSkeleton />
      ) : todos.isError ? (
        <div className="p-4">
          <ErrorState error={todos.error} onRetry={() => todos.refetch()} />
        </div>
      ) : !shown || shown.length === 0 ? (
        <EmptyState>
          {meetingId ? "No To-Dos added in this meeting yet. Add them from an Issue in IDS." : "Nothing here."}
        </EmptyState>
      ) : (
        <ul className="divide-y" aria-label={title}>
          {shown.map((todo) => (
            <TodoRow key={todo.id} todo={todo} />
          ))}
        </ul>
      )}
    </Section>
  );
}

function CompletionSummary({ completion }: { completion: Completion }) {
  const week = formatWeek(completion.week_start);
  if (completion.rate_percent === null) {
    return <span>Last week ({week}): no To-Dos were due</span>;
  }
  const Icon = completion.meets_target ? CircleCheckIcon : TargetIcon;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5">
      <span>Last week ({week}):</span>
      <span
        className={cn(
          "inline-flex items-center gap-1 font-medium",
          completion.meets_target ? "text-success" : "text-destructive",
        )}
      >
        <Icon className="size-3.5" aria-hidden="true" />
        {completion.rate_percent}% done
      </span>
      <span>
        ({completion.done} of {completion.due}) · target {completion.target_percent}%
        <span className="sr-only">{completion.meets_target ? ", target met" : ", below target"}</span>
      </span>
    </span>
  );
}

function TodoRow({ todo }: { todo: Todo }) {
  const { teamId, team, canWrite } = useTeam();
  const toggle = useToggleTodo(teamId);
  const makeIssue = useMakeIssueFromTodo(teamId);
  const done = toggle.isPending ? toggle.variables.done : todo.done_at !== null;
  // The same To-Do can render twice (hidden team page + Conclude), so no id derived from todo.id.
  const checkboxId = useId();

  return (
    <li className="flex items-start gap-3 px-4 py-2.5">
      {canWrite ? (
        <Checkbox
          id={checkboxId}
          className="mt-0.5"
          checked={done}
          onCheckedChange={(checked) => toggle.mutate({ todoId: todo.id, done: checked === true })}
        />
      ) : done ? (
        <CircleCheckIcon className="mt-0.5 size-4 text-success" aria-label="Done" />
      ) : (
        <CircleIcon className="mt-0.5 size-4 text-muted-foreground" aria-label="Not done" />
      )}
      <div className="min-w-0 flex-1">
        <label
          htmlFor={canWrite ? checkboxId : undefined}
          className={cn("block text-sm", done ? "text-muted-foreground line-through" : "font-medium")}
        >
          {todo.title}
        </label>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
          <span>{todo.owner.name}</span>
          <span aria-hidden="true">·</span>
          <span>Due {formatDay(todo.due_date)}</span>
          {todo.overdue && (
            <span className="inline-flex items-center gap-1 rounded-sm bg-destructive-muted px-1 font-medium text-destructive">
              <CircleAlertIcon className="size-3" aria-hidden="true" />
              Overdue
            </span>
          )}
          {todo.done_at && !toggle.isPending && (
            <>
              <span aria-hidden="true">·</span>
              <span>Done {formatInstant(todo.done_at, team.timezone)}</span>
            </>
          )}
          {todo.source_issue && (
            <>
              <span aria-hidden="true">·</span>
              <span>From Issue: {todo.source_issue.title}</span>
            </>
          )}
        </p>
      </div>
      {canWrite && todo.overdue && (
        <Button
          size="xs"
          variant="ghost"
          disabled={makeIssue.isPending}
          onClick={() => makeIssue.mutate(todo.id)}
          aria-label={`Make it an Issue: ${todo.title}`}
        >
          <MessageSquarePlusIcon />
          Make it an Issue
        </Button>
      )}
    </li>
  );
}
