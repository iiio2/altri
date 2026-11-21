"use client";

import { ListPlusIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useTeam } from "@/components/team/team-context";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Issue } from "@/lib/api/types";
import { addDays, formatDayLong } from "@/lib/format";

import { useAddTodo } from "./use-issue-mutations";

const MAX_TITLE = 200;
const DUE_IN_DAYS = 7;

export function AddTodoDialog({ issue }: { issue: Issue }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="ghost">
          <ListPlusIcon />
          Add To-Do
        </Button>
      </DialogTrigger>
      <DialogContent>
        <AddTodoForm issue={issue} onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  );
}

function AddTodoForm({ issue, onDone }: { issue: Issue; onDone: () => void }) {
  const { teamId, team, me } = useTeam();
  const candidates = team.owner_candidates;
  // Default owner: the Issue's owner if they can own To-Dos, else the person adding it, else the first one.
  const defaultOwner =
    candidates.find((u) => u.id === issue.owner.id) ?? candidates.find((u) => u.id === me.user.id) ?? candidates[0];
  const [title, setTitle] = useState("");
  const [ownerId, setOwnerId] = useState(defaultOwner?.id ?? "");
  const addTodo = useAddTodo(teamId);
  const trimmed = title.trim();
  const due = addDays(team.today, DUE_IN_DAYS);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!trimmed || !ownerId) return;
    addTodo.mutate({ issueId: issue.id, title: trimmed, ownerId }, { onSuccess: onDone });
  };

  return (
    <form onSubmit={submit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>Add a To-Do</DialogTitle>
        <DialogDescription>Follow-up for “{issue.title}”</DialogDescription>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor={`todo-title-${issue.id}`}>Title</Label>
        <Input
          id={`todo-title-${issue.id}`}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={MAX_TITLE}
          required
          autoComplete="off"
          placeholder="What needs to happen"
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`todo-owner-${issue.id}`}>Owner</Label>
        <Select value={ownerId} onValueChange={setOwnerId}>
          <SelectTrigger id={`todo-owner-${issue.id}`} className="w-full">
            <SelectValue placeholder="Choose an owner" />
          </SelectTrigger>
          <SelectContent>
            {candidates.map((user) => (
              <SelectItem key={user.id} value={user.id}>
                {user.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <p className="text-sm text-muted-foreground">
        Due <span className="font-medium text-foreground">{formatDayLong(due)}</span> (in {DUE_IN_DAYS} days)
      </p>
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </DialogClose>
        <Button type="submit" disabled={!trimmed || !ownerId || addTodo.isPending}>
          {addTodo.isPending ? "Adding…" : "Add To-Do"}
        </Button>
      </DialogFooter>
    </form>
  );
}
