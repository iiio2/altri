import { CircleCheckIcon, CircleDashedIcon, CircleXIcon, FlagIcon } from "lucide-react";

import type { RockStatus, ScoreStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Status = ScoreStatus | RockStatus;

const STYLES: Record<Status, { label: string; className: string; Icon: typeof CircleCheckIcon }> = {
  on_track: { label: "On track", className: "bg-success-muted text-success", Icon: CircleCheckIcon },
  off_track: { label: "Off track", className: "bg-destructive-muted text-destructive", Icon: CircleXIcon },
  pending: { label: "Pending", className: "bg-muted text-muted-foreground", Icon: CircleDashedIcon },
  complete: { label: "Complete", className: "bg-primary/10 text-foreground", Icon: FlagIcon },
};

export const statusLabel = (status: Status) => STYLES[status].label;

/** Status with icon and text, so it never depends on color alone. */
export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const { label, className: tone, Icon } = STYLES[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap",
        tone,
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}
