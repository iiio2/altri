import type { Metadata } from "next";

import { MeetingRoom } from "@/components/meeting/meeting-room";

export const metadata: Metadata = { title: "Level 10 Meeting" };

/**
 * Opt out of instant-navigation validation: everything below the team layout is per-user data fetched on the
 * client (TanStack Query + live socket), and the layout reads the team id at request time, so there is no
 * static shell for this segment to validate.
 */
export const instant = false;

export default function MeetingPage() {
  return <MeetingRoom />;
}
