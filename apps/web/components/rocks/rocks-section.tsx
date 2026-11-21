"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRightIcon, CircleAlertIcon, CircleCheckIcon, CircleIcon, MessageSquarePlusIcon } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/common/error-state";
import { EmptyState, Section, SectionSkeleton } from "@/components/common/section";
import { StatusBadge } from "@/components/common/status-badge";
import { useTeam } from "@/components/team/team-context";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { api, unwrapWithStatus } from "@/lib/api/client";
import { keys, rocksQuery } from "@/lib/api/queries";
import type { Rock } from "@/lib/api/types";
import { formatDay } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The current quarter's Rocks, read-only; each expands to its Milestones. */
export function RocksSection({ anchor }: { anchor?: string }) {
  const { teamId } = useTeam();
  const rocks = useQuery(rocksQuery(teamId));

  return (
    <Section anchor={anchor} title="Rocks" description={rocks.data ? `${rocks.data.quarter.replace("-", " ")} goals` : "Quarterly goals"}>
      {rocks.isPending ? (
        <SectionSkeleton rows={3} />
      ) : rocks.isError ? (
        <div className="p-4">
          <ErrorState error={rocks.error} onRetry={() => rocks.refetch()} />
        </div>
      ) : rocks.data.rocks.length === 0 ? (
        <EmptyState>No Rocks this quarter.</EmptyState>
      ) : (
        <ul className="divide-y">
          {rocks.data.rocks.map((rock) => (
            <RockRow key={rock.id} rock={rock} />
          ))}
        </ul>
      )}
    </Section>
  );
}

function RockRow({ rock }: { rock: Rock }) {
  const { teamId, canWrite } = useTeam();
  const qc = useQueryClient();
  const makeIssue = useMutation({
    mutationFn: async () => {
      const { data: issue, status } = await unwrapWithStatus(
        api.POST("/api/v1/teams/{team_id}/rocks/{rock_id}/issue", {
          params: { path: { team_id: teamId, rock_id: rock.id } },
        }),
      );
      return { issue, created: status === 201 };
    },
    onSuccess: ({ issue, created }) => {
      void qc.invalidateQueries({ queryKey: [...keys.team(teamId), "issues"] });
      void qc.invalidateQueries({ queryKey: keys.rocks(teamId) });
      if (created) toast.success("Issue created", { description: issue.title });
      else toast.info("Already on the Issues list", { description: issue.title });
    },
    onError: (error) => toast.error("Couldn't make it an Issue", { description: error.message }),
  });
  const done = rock.milestones.filter((m) => m.done).length;

  return (
    <li>
      <Collapsible>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="group/rock flex min-w-48 flex-1 items-start gap-2 rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ChevronRightIcon
                className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]/rock:rotate-90"
                aria-hidden="true"
              />
              <span>
                <span className="block text-sm font-medium">{rock.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {rock.owner.name} · {rock.milestones.length === 0 ? "No Milestones" : `${done} of ${rock.milestones.length} Milestones`}
                </span>
              </span>
            </button>
          </CollapsibleTrigger>
          <div className="flex items-center gap-3">
            <div className="flex w-32 items-center gap-2">
              <Progress value={rock.progress_percent} aria-label={`${rock.title} progress`} className="h-1.5" />
              <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">{rock.progress_percent}%</span>
            </div>
            <StatusBadge status={rock.status} className="w-22 justify-center" />
          </div>
          {canWrite && rock.status === "off_track" && (
            rock.open_issue_id ? (
              <span className="text-xs text-muted-foreground">On the Issues list</span>
            ) : (
              <Button size="xs" variant="ghost" disabled={makeIssue.isPending} onClick={() => makeIssue.mutate()}>
                <MessageSquarePlusIcon />
                Make it an Issue
              </Button>
            )
          )}
        </div>
        <CollapsibleContent>
          {rock.milestones.length === 0 ? (
            <p className="px-11 pb-3 text-sm text-muted-foreground">This Rock has no Milestones.</p>
          ) : (
            <ul className="space-y-1.5 px-11 pb-3" aria-label={`Milestones for ${rock.title}`}>
              {rock.milestones.map((m) => (
                <li key={m.id} className="flex items-center gap-2 text-sm">
                  {m.done ? (
                    <CircleCheckIcon className="size-4 text-success" aria-label="Done" />
                  ) : m.past_due ? (
                    <CircleAlertIcon className="size-4 text-destructive" aria-label="Past due" />
                  ) : (
                    <CircleIcon className="size-4 text-muted-foreground" aria-label="Not done" />
                  )}
                  <span className={cn("flex-1", m.done && "text-muted-foreground")}>{m.title}</span>
                  <span className={cn("text-xs tabular-nums", m.past_due ? "font-medium text-destructive" : "text-muted-foreground")}>
                    {m.past_due ? "Past due · " : ""}
                    {formatDay(m.due_date)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}
