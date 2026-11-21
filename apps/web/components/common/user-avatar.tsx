import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

export function UserAvatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground",
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
