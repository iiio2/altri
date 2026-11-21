"use client";

import { useEffect, useState } from "react";

import type { MeetingState } from "@/lib/api/types";

/**
 * The section timer as the server owns it: `section_elapsed_seconds` at the moment the snapshot was built,
 * advanced by this browser's monotonic clock since the snapshot arrived. Never reads the wall clock, so a
 * browser with a wrong system time still shows the same timer as everyone else. Ended meetings are frozen.
 */
export function useSectionClock(meeting: MeetingState | null | undefined) {
  const [now, setNow] = useState(() => performance.now());
  const running = meeting?.status === "active";

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(performance.now()), 250);
    return () => clearInterval(id);
  }, [running]);

  if (!meeting) return null;
  const drift = running ? Math.max(0, (now - meeting.received_at) / 1000) : 0;
  const elapsed = meeting.section_elapsed_seconds + drift;
  const duration = meeting.section_duration_seconds;
  return {
    elapsed,
    duration,
    remaining: duration - elapsed,
    overTime: meeting.over_time || elapsed > duration,
  };
}
