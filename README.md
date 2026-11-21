# Altri

A small weekly leadership-meeting app modelled on the EOS edition of Ninety.io. Each leadership team gets one place
to track how the business is doing and to run its weekly meeting:

```
Measure            →  Commit                 →  Resolve
(weekly Scorecard)    (Rocks and To-Dos)        (Issues solved in the meeting)
```

- **Scorecard**: weekly numbers per Measurable, with goals. You can turn any off-track cell into an Issue.
- **Rocks**: quarterly goals with milestones. Their status is computed, not stored.
- **To-Dos**: short-term tasks. Overdue To-Dos can be raised as Issues.
- **Issues**: prioritised, solved during the meeting, and can create To-Dos.
- **Weekly meeting**: Scorecard (5 min) → IDS (60 min) → Conclude (10 min). It syncs live between browsers over a
  WebSocket, uses a server-owned timer, collects attendee ratings and produces an end-of-meeting summary.

There are three roles. **Admins** can act in every team, **Team Members** can write in their own teams, and
**Observers** can only read. The server enforces every role and team-boundary rule.

## Stack

| | |
|---|---|
| Monorepo | pnpm workspace: `apps/web`, `apps/api` |
| Web (`apps/web`) | Next.js 16 (App Router, Turbopack, React Compiler), React 19, TypeScript, Tailwind CSS 4, TanStack Query, oxlint |
| API (`apps/api`) | FastAPI on Python 3.14 (managed with `uv`), SQLAlchemy 2 async with psycopg 3, Alembic, pytest, ruff |
| Database | Postgres (Neon or local; Postgres 18 in Docker) |

```
apps/
  web/            Next.js app: login (user switcher), team workspace, live meeting room
  api/
    src/altri_api/  one package per feature (scorecard, issues, todos, rocks, meetings, teams, auth, live)
                    rules.py: spec 2.6 rules as pure functions · calendar.py: company-time week math
                    clock.py: the only source of "now"
    migrations/     Alembic (constraints live in the database, not only in the app)
    tests/          API, rule, constraint and live-socket tests
docs/             spec, seed notes and seed.json (git-ignored, local only)
compose.yaml      the whole stack in Docker
```

## Prerequisites

- `docs/seed.json`. The `docs/` folder is git-ignored, so get it separately and place it at `docs/seed.json`. Both the
  seed script and the API Docker image read it.
- **Docker only:** Docker with Compose.
- **Local development:** Node 26, pnpm (the version is pinned in `package.json` → `packageManager`; Corepack picks
  it up), [`uv`](https://docs.astral.sh/uv/) on your `PATH`, and a Postgres database.

## Quick start: Docker

```bash
docker compose up --build
```

Open <http://localhost:3000> and pick a seeded user to sign in. Login is passwordless.

Compose starts Postgres 18, runs the migrations and the seed once through the `setup` service, then starts the API
on :8000 and the web app on :3000. Stop any local `pnpm dev` first, because it uses the same ports.

- Every `up` reruns the migrations and the idempotent seed. Edits made in the app are kept.
- Reset to a fresh seed: `docker compose run --rm setup python -m altri_api.seed --reset`
- Wipe the database: `docker compose down -v`
- The browser opens the live WebSocket directly to `<page host>:8000`, so port 8000 must stay published.

## Quick start: local development

```bash
cp .env.example .env   # then set DATABASE_URL
pnpm i                 # JS deps; the api package's postinstall runs `uv sync` for Python deps
pnpm db:migrate
pnpm db:seed
pnpm dev               # web on http://localhost:3000, API on http://localhost:8000 (docs at /docs)
```

The web app proxies `/api/v1/*` to the API (`API_URL`, default `http://127.0.0.1:8000`), so the session cookie
stays first-party. The live WebSocket connects to the API directly on port 8000. To point it elsewhere, set
`NEXT_PUBLIC_API_WS_URL`.

## Configuration

All settings come from environment variables or the repo-root `.env`. See [.env.example](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | (none) | Postgres connection URL. With Neon's pooler, prepared statements are disabled. |
| `TEST_DATABASE_URL` | `<db>_test` | Database the tests rebuild on every run |
| `APP_NOW` | `2026-11-11T15:00:00Z` | The app's "now" in UTC. Business logic never reads the system clock. |
| `APP_CLOCK` | `ticking` | `ticking` = `APP_NOW` + time since the API started, so meeting timers run. `frozen` = exactly `APP_NOW`. |
| `CORS_ORIGINS` | localhost:3000 | Browser origins allowed to call the API and open the live socket (JSON list) |
| `SESSION_COOKIE_SECURE` | `false` | Set to `true` behind HTTPS |

Time rules: timestamps are stored in UTC. The company time zone is `America/Chicago`, and weeks run Monday–Sunday in
company time and are identified by their Monday.

## Commands

Run these from the repo root.

| Command | What it does |
|---|---|
| `pnpm i` | Install web and api dependencies (runs `uv sync`) |
| `pnpm dev` · `pnpm dev:web` · `pnpm dev:api` | Run both apps, or one of them |
| `pnpm build` | Production build of the web app |
| `pnpm lint` | oxlint (web; warnings fail) and ruff (api) |
| `pnpm typecheck` | TypeScript check of the web app |
| `pnpm db:migrate` | `alembic upgrade head` |
| `pnpm db:seed` | Idempotent seed. Inserts missing seed rows and never overwrites app edits. |
| `pnpm db:reset` | Back to the freshly seeded state |
| `pnpm test:api` | API tests. Rebuilds the test database from migrations and the seed, with the clock frozen at `APP_NOW`. |
| `pnpm rules:report` | Spec 2.6 rule values as JSON, evaluated exactly at `APP_NOW` |
| `pnpm --filter web gen:api` | Regenerate the web app's typed API client from the FastAPI OpenAPI schema |

To regenerate the committed `rules_report.json`, start from a fresh seed (`pnpm db:reset`) and run:

```bash
pnpm --filter api rules:report --out ../../rules_report.json
```

New migration: `cd apps/api && uv run alembic revision --autogenerate -m "..."`

## Testing

`pnpm test:api` runs the backend suite. It covers rules, authorization, database constraints, every API area and
the live socket. Each run builds one test database through the real migrations and loads `seed.json`. The clock is
frozen, and tests that write restore the seeded state afterwards, so test order never matters.

Against remote Neon each query takes about 350 ms, so the suite takes several minutes. Against a local Postgres it
takes seconds. For example, with the Compose database running:

```bash
TEST_DATABASE_URL=postgresql://altri:altri@localhost:5432/altri_test pnpm test:api
```

End-to-end browser tests (Playwright, two-browser meeting sync) are not set up yet.

