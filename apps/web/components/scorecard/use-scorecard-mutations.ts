"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, unwrap, unwrapWithStatus } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import type { Cell, Scorecard } from "@/lib/api/types";

type CellRef = { measurableId: string; week: string };

function patchCell(card: Scorecard | undefined, ref: CellRef, patch: (cell: Cell) => Cell): Scorecard | undefined {
  if (!card) return card;
  return {
    ...card,
    measurables: card.measurables.map((row) =>
      row.id !== ref.measurableId
        ? row
        : { ...row, cells: row.cells.map((c) => (c.week_start === ref.week ? patch(c) : c)) },
    ),
  };
}

/** Enter, change or clear a score. Last save wins (no `expected_version`), as the spec asks. */
export function useSetScore(teamId: string) {
  const qc = useQueryClient();
  const key = keys.scorecard(teamId);

  return useMutation({
    mutationFn: ({ measurableId, week, value }: CellRef & { value: number | null }) =>
      unwrap(
        api.PUT("/api/v1/teams/{team_id}/measurables/{measurable_id}/scores/{week_start}", {
          params: { path: { team_id: teamId, measurable_id: measurableId, week_start: week } },
          body: { value },
        }),
      ),
    onMutate: async (vars) => {
      // Show the typed value at once; its status arrives with the response.
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<Scorecard>(key);
      qc.setQueryData<Scorecard>(key, (card) => patchCell(card, vars, (c) => ({ ...c, value: vars.value })));
      return { previous };
    },
    onSuccess: (cell, vars) => {
      qc.setQueryData<Scorecard>(key, (card) => patchCell(card, vars, () => cell));
    },
    onError: (error, _vars, context) => {
      if (context?.previous) qc.setQueryData(key, context.previous);
      toast.error("Score not saved", { description: error.message });
    },
  });
}

/** Make it an Issue on an off-track cell. Idempotent on the server: 200 returns the Issue already open. */
export function useMakeIssueFromScore(teamId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ measurableId, week }: CellRef) => {
      const { data: issue, status } = await unwrapWithStatus(
        api.POST("/api/v1/teams/{team_id}/measurables/{measurable_id}/scores/{week_start}/issue", {
          params: { path: { team_id: teamId, measurable_id: measurableId, week_start: week } },
        }),
      );
      return { issue, created: status === 201 };
    },
    onSuccess: ({ issue, created }, vars) => {
      qc.setQueryData<Scorecard>(keys.scorecard(teamId), (card) =>
        patchCell(card, vars, (c) => ({ ...c, open_issue_id: issue.id })),
      );
      void qc.invalidateQueries({ queryKey: [...keys.team(teamId), "issues"] });
      if (created) toast.success("Issue created", { description: issue.title });
      else toast.info("Already on the Issues list", { description: issue.title });
    },
    onError: (error) => toast.error("Couldn't make it an Issue", { description: error.message }),
  });
}
