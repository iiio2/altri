"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, unwrap, unwrapWithStatus } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";

/**
 * Mark done or undo. The row renders `variables.done` while the request is in flight (optimistic without
 * touching the cache), then the refetched list brings the server's done time, overdue flag and completion.
 */
export function useToggleTodo(teamId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ todoId, done }: { todoId: string; done: boolean }) =>
      unwrap(
        api.PATCH("/api/v1/teams/{team_id}/todos/{todo_id}", {
          params: { path: { team_id: teamId, todo_id: todoId } },
          body: { done },
        }),
      ),
    onError: (error) => toast.error("To-Do not updated", { description: error.message }),
    onSettled: () => qc.invalidateQueries({ queryKey: [...keys.team(teamId), "todos"] }),
  });
}

/** Make an overdue To-Do an Issue. Idempotent: 200 returns the Issue already open for it. */
export function useMakeIssueFromTodo(teamId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (todoId: string) => {
      const { data: issue, status } = await unwrapWithStatus(
        api.POST("/api/v1/teams/{team_id}/todos/{todo_id}/issue", {
          params: { path: { team_id: teamId, todo_id: todoId } },
        }),
      );
      return { issue, created: status === 201 };
    },
    onSuccess: ({ issue, created }) => {
      void qc.invalidateQueries({ queryKey: [...keys.team(teamId), "issues"] });
      if (created) toast.success("Issue created", { description: issue.title });
      else toast.info("Already on the Issues list", { description: issue.title });
    },
    onError: (error) => toast.error("Couldn't make it an Issue", { description: error.message }),
  });
}
