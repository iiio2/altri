import { IssuesSection } from "@/components/issues/issues-section";
import { MeetingBanner } from "@/components/meeting/meeting-banner";
import { RocksSection } from "@/components/rocks/rocks-section";
import { ScorecardSection } from "@/components/scorecard/scorecard-section";
import { TeamHeading } from "@/components/team/team-heading";
import { TodosSection } from "@/components/todos/todos-section";

/**
 * Opt out of instant-navigation validation: everything below the team layout is per-user data fetched on the
 * client (TanStack Query + live socket), and the layout reads the team id at request time, so there is no
 * static shell for this segment to validate.
 */
export const instant = false;

/** Team page, laid out along the weekly loop: Measure (Scorecard), Commit (Rocks, To-Dos), Resolve (Issues). */
export default function TeamPage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6">
      <TeamHeading />
      <MeetingBanner />
      <ScorecardSection anchor="scorecard" />
      <div className="grid items-start gap-6 lg:grid-cols-[3fr_2fr]">
        <IssuesSection anchor="issues" />
        <TodosSection anchor="todos" />
      </div>
      <RocksSection anchor="rocks" />
    </main>
  );
}
