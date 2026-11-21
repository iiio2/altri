"use client";

import { PlusIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { PrioritySelect } from "./priority-select";
import { useCreateIssue } from "./use-issue-mutations";

const MAX_TITLE = 200;

/** Title required, priority optional; the person adding it becomes the owner. */
export function NewIssueForm({ teamId }: { teamId: string }) {
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<number | null>(null);
  const create = useCreateIssue(teamId);
  const trimmed = title.trim();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!trimmed) return;
    create.mutate(
      { title: trimmed, priority },
      {
        onSuccess: () => {
          setTitle("");
          setPriority(null);
        },
      },
    );
  };

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
      <Input
        aria-label="New Issue title"
        placeholder="Add an Issue…"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        maxLength={MAX_TITLE}
        autoComplete="off"
        className="h-8 min-w-48 flex-1"
      />
      <PrioritySelect value={priority} onChange={setPriority} label="Priority for the new Issue" className="h-8" />
      <Button type="submit" size="default" disabled={!trimmed || create.isPending}>
        <PlusIcon />
        {create.isPending ? "Adding…" : "Add"}
      </Button>
    </form>
  );
}
