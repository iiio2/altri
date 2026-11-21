import { UserAvatar } from "@/components/common/user-avatar";
import type { MeetingState } from "@/lib/api/types";
import { roleLabel } from "@/lib/format";

export function AttendeesPanel({ meeting }: { meeting: MeetingState }) {
  return (
    <section aria-labelledby="attendees-heading" className="rounded-lg border bg-card">
      <h2 id="attendees-heading" className="border-b px-4 py-3 text-base font-semibold tracking-tight">
        Attendees <span className="font-normal text-muted-foreground">({meeting.attendees.length})</span>
      </h2>
      <ul className="space-y-2 p-3" aria-live="polite">
        {meeting.attendees.map((a) => (
          <li key={a.id} className="flex items-center gap-2.5">
            <UserAvatar name={a.name} className="size-7" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{a.name}</span>
              <span className="block text-xs text-muted-foreground">
                {a.id === meeting.facilitator.id ? "Facilitator" : roleLabel[a.role]}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
