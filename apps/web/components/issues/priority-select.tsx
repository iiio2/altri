"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const NONE = "none";
const LEVELS = [5, 4, 3, 2, 1] as const;

export function priorityLabel(priority: number | null): string {
  return priority === null ? "No priority" : `Priority ${priority}`;
}

/** Priority 5 (most urgent) to 1, or none (sorted last). */
export function PrioritySelect({
  value,
  onChange,
  disabled,
  label,
  className,
}: {
  value: number | null;
  onChange: (priority: number | null) => void;
  disabled?: boolean;
  label: string;
  className?: string;
}) {
  return (
    <Select
      value={value === null ? NONE : String(value)}
      onValueChange={(v) => onChange(v === NONE ? null : Number(v))}
      disabled={disabled}
    >
      <SelectTrigger size="sm" aria-label={label} className={cn("w-20 tabular-nums", className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {LEVELS.map((level) => (
          <SelectItem key={level} value={String(level)}>
            P{level}
          </SelectItem>
        ))}
        <SelectItem value={NONE}>None</SelectItem>
      </SelectContent>
    </Select>
  );
}

/** Read-only priority, for Observers. */
export function PriorityTag({ value }: { value: number | null }) {
  return (
    <span
      aria-label={priorityLabel(value)}
      className="inline-flex h-7 w-20 items-center rounded-md border px-2.5 text-[0.8rem] text-muted-foreground tabular-nums"
    >
      {value === null ? "None" : `P${value}`}
    </span>
  );
}
