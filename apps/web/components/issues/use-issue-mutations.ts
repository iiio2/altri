"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, isApiError, unwrap } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import type { Issue } from "@/lib/api/types";

function useInvalidate(teamId: string) {
  const qc = useQueryClient();
  return (...resources: ("issues" | "todos" | "scorecard" | "rocks")[]) =>
    Promise.all(resources.map((r) => qc.invalidateQueries({ queryKey: [...keys.team(teamId), r] })));
}

export function useCreateIssue(teamId: string) {
  const invalidate = useInvalidate(teamId);
  return useMutation({
    mutationFn: (body: { title: string; priority: number | null }) =>
      unwrap(api.POST("/api/v1/teams/{team_id}/issues", { params: { path: { team_id: teamId } }, body })),
    onSuccess: () => invalidate("issues"),
    onError: (error) => toast.error("Issue not added", { description: error.message }),
  });
}

/**
 * Sends the version the user saw, so a priority someone else changed in the meantime is not silently
 * overwritten (409 → show the latest list instead).
 */
export function useSetPriority(teamId: string) {
  const qc = useQueryClient();
  const key = keys.issues(teamId, "open");
  return useMutation({
    mutationFn: ({ issue, priority }: { issue: Issue; priority: number | null }) =>
      unwrap(
        api.PATCH("/api/v1/teams/{team_id}/issues/{issue_id}", {
          params: { path: { team_id: teamId, issue_id: issue.id } },
          body: { priority, expected_version: issue.version },
        }),
      ),
    onMutate: async ({ issue, priority }) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<Issue[]>(key);
      qc.setQueryData<Issue[]>(key, (list) => list?.map((i) => (i.id === issue.id ? { ...i, priority } : i)));
      return { previous };
    },
    onError: (error, _vars, context) => {
      if (context?.previous) qc.setQueryData(key, context.previous);
      if (isApiError(error, 409)) {
        toast.warning("Someone else just changed this Issue", { description: "Showing the latest version." });
      } else {
        toast.error("Priority not saved", { description: error.message });
      }
    },
    // Re-sort in Issue order (priority, then age) as the server defines it.
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useSolveIssue(teamId: string) {
  const invalidate = useInvalidate(teamId);
  return useMutation({
    mutationFn: ({ issueId, note }: { issueId: string; note: string }) =>
      unwrap(
        api.POST("/api/v1/teams/{team_id}/issues/{issue_id}/solve", {
          params: { path: { team_id: teamId, issue_id: issueId } },
          body: { resolution_note: note },
        }),
      ),
    onSuccess: (issue) => {
      toast.success("Issue solved", { description: issue.title });
      return invalidate("issues", "scorecard", "rocks", "todos");
    },
    onError: (error) => toast.error("Issue not solved", { description: error.message }),
  });
}

export function useAddTodo(teamId: string) {
  const invalidate = useInvalidate(teamId);
  return useMutation({
    mutationFn: ({ issueId, title, ownerId }: { issueId: string; title: string; ownerId: string }) =>
      unwrap(
        api.POST("/api/v1/teams/{team_id}/issues/{issue_id}/todos", {
          params: { path: { team_id: teamId, issue_id: issueId } },
          body: { title, owner_id: ownerId },
        }),
      ),
    onSuccess: (todo) => {
      toast.success("To-Do added", { description: `${todo.title} · ${todo.owner.name}` });
      return invalidate("todos");
    },
    onError: (error) => toast.error("To-Do not added", { description: error.message }),
  });
}
