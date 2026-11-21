# Altri API

FastAPI + SQLAlchemy 2 (async, psycopg 3) + Postgres. Interactive docs at `/docs` (OpenAPI at `/openapi.json`).

## Run

```bash
pnpm db:migrate        # alembic upgrade head
pnpm db:seed           # idempotent: inserts missing seed rows, never overwrites app edits
pnpm db:reset          # back to the freshly seeded state (drops Scores/Issues/To-Dos/meetings/sessions, reseeds)
pnpm dev:api           # http://localhost:8000
pnpm test:api          # rebuilds <db>_test from migrations + seed, clock frozen at APP_NOW
pnpm rules:report      # spec 2.6 values as JSON, exactly at APP_NOW (run on a fresh seed)
```

Settings (env or repo-root `.env`): `DATABASE_URL`, `APP_NOW` (default `2026-11-11T15:00:00Z`), `APP_CLOCK`
(`ticking` | `frozen`), `CORS_ORIGINS`, `SESSION_COOKIE_SECURE`, `TEST_DATABASE_URL`.

**Fixtures and clock in tests.** One database per run, rebuilt through the real migrations and loaded from
`seed.json`. `APP_CLOCK=frozen`, so every request sees exactly `APP_NOW`; tests move time with `set_now`. Tests
that write use `fresh_data`, which restores the seeded state afterwards, so order never matters. Against remote
Neon each query is ~350 ms; with `TEST_DATABASE_URL` on a local Postgres the suite runs in seconds.

## API map (`/api/v1`)

| Area | Endpoints |
|---|---|
| Auth | `GET /auth/users` · `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` |
| Teams | `GET /teams` · `GET /teams/{t}` (members, `owner_candidates`, today / current week / quarter) |
| Scorecard | `GET /teams/{t}/scorecard` · `PUT /teams/{t}/measurables/{m}/scores/{week}` · `POST …/scores/{week}/issue` (Make it an Issue) |
| Issues | `GET/POST /teams/{t}/issues` (`?status=open\|solved`) · `GET/PATCH /teams/{t}/issues/{i}` (priority) · `POST …/solve` · `POST …/todos` |
| To-Dos | `GET /teams/{t}/todos` (+ last closed week's completion) · `PATCH /teams/{t}/todos/{id}` (`done`) · `POST …/issue` (overdue only) |
| Rocks | `GET /teams/{t}/rocks` (`?quarter=`; read-only) · `POST /teams/{t}/rocks/{r}/issue` (off-track only) |
| Meetings | `GET/POST /teams/{t}/meetings` · `GET …/active` · `GET …/{id}` · `POST …/{id}/join` · `PUT …/{id}/section` · `PUT …/{id}/rating` · `POST …/{id}/end` · `GET …/{id}/summary` |
| Live | `WS /teams/{t}/live` |

Status codes: 401 no session · 403 unreadable team (same answer for unknown ids) or wrong role · 404 unknown item
inside a readable team · 409 the item's state forbids it (solved, ended, not off track, stale `expected_version`) ·
422 invalid input. Request bodies reject unknown fields. All timestamps are UTC (`…Z`); weeks are their Monday
(`YYYY-MM-DD`, company time); due dates are company-time dates.

**Live protocol.** On connect: `hello` with the current meeting state (or null). Then `meeting` (full state on
every start/join/section/rating/end) and `changed` (`["scorecard","issues",…]`: refetch over REST). `ping` gets
`pong` with `server_now`. Mutations only go through REST.

## Decisions (spec 2.8)

**1. Data model.** Every team-scoped row carries `team_id`, and every link is a composite FK on `(id, team_id)`, so
the database refuses an Issue sourced from another team's Measurable or a To-Do linked to another team's Issue.
An Issue's source is up to one of: `(source_measurable_id, source_week_start)` (a Scorecard cell),
`source_rock_id`, or `source_todo_id` (CHECK `num_nonnulls(...) <= 1`). A To-Do links to its Issue through
`source_issue_id`. Meeting membership of work is explicit: `issues.solved_in_meeting_id` and
`todos.created_in_meeting_id` are stamped (inside the same SQL statement) when the team has a running meeting,
and backfilled for the seed from the meeting windows. Scores are `(measurable_id, week_start)` with
`week_start` a Monday (CHECK) and `NUMERIC(16,4)` values (exact goal comparisons). Rock and Measurable statuses
aren't stored: they're computed by `rules.py` from seeded inputs, so they can't go stale. Cross-table rules
(owners are never Observers, and are team members or Admins; Observers can't rate) are a trigger, because a
CHECK can't see other tables. Tradeoff: composite keys and triggers are more DDL, but integrity doesn't depend on
the API being the only writer.

**2. API.** Resource-oriented REST, nested under `/teams/{team_id}` so one dependency (`ReadableTeam` /
`WritableTeam`) authorizes every route before any handler runs. Actions that are state transitions are verbs
(`/solve`, `/end`, `/join`, `…/issue`). Section changes name the target section (`PUT …/section
{"section":"ids"}`), so a retried or double-clicked "next" is a no-op instead of skipping a section. Scores and
Issue priority are last-save-wins, with an optional `expected_version` (409 on mismatch) for clients that want
lost-update protection.

**3. Real time.** A per-team WebSocket. The `meetings` row is the single source of truth (section,
`section_started_at`); the socket only pushes. The server owns the timer: clients render
`section_elapsed_seconds` as of `server_now` and tick locally, and `over_time` is computed server-side; sections
never auto-advance. Recovery is "snapshot on connect": a late join, refresh, or reconnect (facilitator included)
gets the full state in `hello`, so missed messages don't matter. A slow consumer is disconnected and reconnects.
The socket checks `Origin` against `CORS_ORIGINS` (stops cross-site hijacking of the cookie session) and
re-checks the session every 60 s. Tradeoff: the hub is in-process, so the API runs as one worker; scaling out
means putting Postgres `LISTEN/NOTIFY` or Redis behind the same `publish`/`subscribe` interface. WebSocket rather
than SSE because it's one connection per client that can also carry pings for clock-offset measurement.

**4. Duplicate-free Make it an Issue.** A partial unique index allows one *unsolved* Issue per source
(`… WHERE solved_at IS NULL`). The endpoint does `INSERT … ON CONFLICT DO NOTHING RETURNING id`; if nothing was
inserted it selects the existing unsolved Issue. Under a race the second insert blocks on the first's
uncommitted index entry, then conflicts, and its follow-up SELECT (a new READ COMMITTED snapshot) returns the
winner. No application locks, no check-then-insert gap; the test fires 12 parallel requests and gets one row.
Response: 201 for the creator, 200 with the same Issue for everyone else.

**5. Keeping past summaries unchanged (described, not built).** Today summaries are computed from live data,
evaluated as of the meeting's start. To freeze them, write an immutable `meeting_summaries` row (JSONB, plus a
schema version) in the same transaction that sets `ended_at`, and serve that row; the seeded meetings get one
from a migration. Rows are insert-only (no UPDATE grant / trigger). The cost is storing denormalized names and
values, which is exactly the point: renaming a Measurable or editing a Score later must not rewrite history.

## Calls made where the spec was open

- **Clock.** A frozen `APP_NOW` would stop meeting timers, so `APP_CLOCK=ticking` (default) is APP_NOW plus the
  time since the process started (monotonic). Business dates stay on the seed's day; restarting resets to APP_NOW.
  Writes clamp so a restart can't produce an end before a start. Tests and the rules report use exactly APP_NOW.
- **To-Do owners** are the team's Team Members plus Admins (Admins act in every team). Same rule in the API and
  the trigger. Any writer in the team can mark any To-Do done; marking done twice keeps the first time.
- **Make it an Issue** is refused (409) for cells that aren't off track, unless an unsolved Issue already exists.
  Scores can be entered for any past or the current week, not future ones; `null` clears a score.
- **To-Dos** can be added to solved Issues too (follow-ups are often written right after solving).
- **Rating** is accepted only in Conclude, from attendees who are Admins or Team Members, until the end.
- **Rules report** includes every Rock of each team (not only the current quarter) and every ended meeting.
- **Seed reruns** upsert reference data (teams, users, Measurables, Rocks) but never overwrite Scores, Issues,
  To-Dos or meetings the app has changed; `pnpm db:reset` restores the seed exactly.

## Known limitations

- One API worker (in-process live hub; see 3). Sessions don't expire mid-socket for up to 60 s.
- Summaries are live, not snapshotted (see 5).
- The ticking clock resets to APP_NOW on restart, so wall time between restarts isn't continuous.
