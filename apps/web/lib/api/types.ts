import type { components } from "./schema";

type S = components["schemas"];

export type User = S["UserOut"];
export type UserRef = S["UserRef"];
export type Role = User["role"];
export type Me = S["MeOut"];
export type Team = S["TeamOut"];
export type TeamDetail = S["TeamDetailOut"];

export type Scorecard = S["ScorecardOut"];
export type MeasurableRow = S["MeasurableRowOut"];
export type Cell = S["CellOut"];
export type Goal = S["GoalOut"];
export type ScoreStatus = Cell["status"];

export type Issue = S["IssueOut"];
export type IssueSource = NonNullable<Issue["source"]>;

export type Todo = S["TodoOut"];
export type TodoList = S["TodoListOut"];
export type Completion = S["CompletionOut"];

export type Rock = S["RockOut"];
export type Rocks = S["RocksOut"];
export type RockStatus = Rock["status"];

export type MeetingSection = S["MeetingStateOut"]["section"];
export type MeetingSummary = S["MeetingSummaryOut"];

/**
 * Meeting state as the server sent it, plus when this browser received it (a `performance.now()` reading).
 * The timer is `section_elapsed_seconds` advanced by the local monotonic clock since receipt, so every browser
 * shows the server's timer regardless of its own wall clock.
 */
export type MeetingState = S["MeetingStateOut"] & { received_at: number };
