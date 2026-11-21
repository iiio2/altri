"use client";

import { CheckIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Issue } from "@/lib/api/types";

import { useSolveIssue } from "./use-issue-mutations";

const MAX_NOTE = 2000;

export function SolveIssueDialog({ teamId, issue }: { teamId: string; issue: Issue }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <CheckIcon />
          Solve
        </Button>
      </DialogTrigger>
      <DialogContent>
        {/* Mounted only while open, so the note starts empty each time. */}
        <SolveForm teamId={teamId} issue={issue} onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  );
}

function SolveForm({ teamId, issue, onDone }: { teamId: string; issue: Issue; onDone: () => void }) {
  const [note, setNote] = useState("");
  const solve = useSolveIssue(teamId);
  const trimmed = note.trim();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!trimmed) return;
    solve.mutate({ issueId: issue.id, note: trimmed }, { onSuccess: onDone });
  };

  return (
    <form onSubmit={submit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>Solve Issue</DialogTitle>
        <DialogDescription>{issue.title}</DialogDescription>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor={`solve-note-${issue.id}`}>How was it solved?</Label>
        <Textarea
          id={`solve-note-${issue.id}`}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={MAX_NOTE}
          required
          rows={4}
          placeholder="The decision, and who does what next"
        />
        <p className="text-xs text-muted-foreground">Required. Add follow-ups as To-Dos.</p>
      </div>
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </DialogClose>
        <Button type="submit" disabled={!trimmed || solve.isPending}>
          {solve.isPending ? "Solving…" : "Mark solved"}
        </Button>
      </DialogFooter>
    </form>
  );
}
