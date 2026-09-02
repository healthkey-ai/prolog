# Deploying PROlog

> **Design revision 2026-08-31 — read this first.** PROlog is becoming a Django
> app inside **PRomop, which owns the database**: no PROlog datastore, every
> response bound to a PRomop `Person`, and an email question that creates a
> patient account rather than a mailing-list row. See
> [requirements.md](requirements.md) "Changes in this revision".
>
> **The code still ships the two profiles this page documents.** Everything
> below is accurate for the current release and stays supported until the
> phase 0/2 work lands; what changes then is that `PROLOG_PROFILE` and the
> standalone schema go away, not how definitions and themes are mounted.

**Requirements:** DEP-1…DEP-7, NFR-1, NFR-5 in [requirements.md](requirements.md). Installing inside a host platform: [integration.md](integration.md).

## What a deployment is

One container image (backend + built runner, served by WhiteNoise) plus
PostgreSQL 18, with two directories mounted from the customer's private
repository:

```
/data/surveys/   ← PROLOG_DEFINITION_DIRS   survey definition JSON files
/data/themes/    ← PROLOG_THEME_DIRS        theme directories (theme.json + assets)
```

Nothing customer-specific is baked into the image. Upgrading PROlog is a
tag bump; changing content is a file change plus a reload/activation.

## Quick start

```sh
cp .env.example .env            # set SECRET_KEY, POSTGRES_PASSWORD, ALLOWED_HOSTS, CORS, public URL, data dir
docker compose --profile app up -d --build
docker compose exec app python manage.py load_definition /data/surveys --activate
open https://survey.example.org/s/<slug>   # or http://localhost:8000/... with SECURE_SSL_REDIRECT=false
```

The container runs `migrate` and `load_definitions` (drafts) at start; a
survey goes live only when a version is activated explicitly. A definition
file that cannot be loaded (invalid, truncated, not UTF-8) is reported in
the container log and skipped; the others load and the app still starts.
The database is published on the host's loopback interface only, and the
app runs as an unprivileged user (`app`) with a read-only `/app`; the
directories mounted under `/data` must be readable by that user (world-
readable files, or owned by its uid: `docker compose exec app id -u`), or
`load_definitions` cannot run and the container starts with the
definitions already in the database (the exit code is in its log).

## Promotion flow (validate → load → review → activate)

1. `manage.py validate_definition surveys/<slug>.json` — schema + semantic
   rules (DAG, options, limits, translations). Fix every error; read the
   warnings.
2. `manage.py register_theme themes/<code>` — theme schema, assets, contrast.
3. `manage.py load_definition surveys/<slug>.json` — loads/updates the
   **draft**. Drafts are not served by the runner.
4. Review the draft on a staging deployment (activate it there).
5. `manage.py load_definition surveys/<slug>.json --activate` — activates
   the version, archiving the previously active one. Activation is refused
   while any language is `translation_status: machine`.
6. Smoke test: open the survey, complete one response, `export_responses`.

Any wording or structure change after activation requires a **new
`version`**; the loader refuses to modify a published version.

## Environment

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `PROLOG_PUBLIC_URL` | Django/CORS basics and the public origin used in links |
| `DEBUG` | `false` unless set to `true`. The image sets `DEBUG=false`; a bare-host install should set it too. `manage.py` uses the development settings (`DEBUG` on, development key accepted) only while *neither* `DEBUG` nor `SECRET_KEY` is in the environment, so a cron job that exports `SECRET_KEY` runs with production settings; `pytest` always uses `prolog.settings_dev` |
| `POSTGRES_*` | database connection (no SQLite fallback). `POSTGRES_PASSWORD` has no default in the compose file: it must be set in `.env` |
| `PROLOG_PROFILE` | `standalone` (default) or `integrated`. Being retired: the 2026-08-31 revision makes PRomop-hosted the only shape. |
| `PROLOG_DEFINITION_DIRS`, `PROLOG_THEME_DIRS` | path-separated directory lists |
| `PROLOG_THROTTLE_CREATE/CAPTURE/ANSWER/READ/WRITE` | throttle rates per hashed client address (create `30/hour`, contact/identity capture `30/hour`, answer `600/hour` per response, read `1200/hour`, answer/submit writes `3000/hour` per client). Behind NAT (clinic Wi-Fi, mobile carriers) many participants share one address: raise `CREATE`/`CAPTURE` (and `WRITE`, which counts every participant's saves) accordingly |
| `CACHE_BACKEND`, `CACHE_LOCATION` | where throttle counters live. Default: an in-process cache, so each gunicorn worker counts separately and every rate is effectively multiplied by `WEB_CONCURRENCY`. For exact limits use a cache shared by all workers, e.g. `CACHE_BACKEND=django.core.cache.backends.redis.RedisCache CACHE_LOCATION=redis://cache:6379/1` |
| `PROLOG_ABANDONED_RESPONSE_DAYS` | retention of in-progress responses in days (default 90, at least 1: `0` would delete every in-progress response and is refused) |
| `TIME_ZONE` | IANA zone (default `UTC`) in which calendar dates are taken: a survey's `effective_from`/`effective_to`, the due dates of repeat schedules and the daily `send_due_invitations` cycle, and contacts' `captured_on`. Set the deployment's local zone; the integrated profile uses the host project's `TIME_ZONE` |
| `PROLOG_CLIENT_KEY_SALT` | salt for the hashed client keys (throttle counters, `user_agent_hash`); defaults to `SECRET_KEY`, so it only needs setting to rotate the hashes independently of the key. A placeholder value (`prolog`, `change-me`) is refused at start |
| `EMAIL_BACKEND`, `PROLOG_EMAIL_FROM` | mail backend and sender for invitation emails (`send_due_invitations`, both profiles). The console backend is the default; `PROLOG_PUBLIC_URL` must be the real public origin: invitations are not sent while it points at localhost outside `DEBUG` |
| `SECURE_SSL_REDIRECT` | `true` by default when `DEBUG=false` (the compose file keeps that default); `/api/health/` is exempt. Set `false` only to try the image over plain HTTP on localhost |
| `PROLOG_NUM_PROXIES` | number of reverse proxies in front of the app (default `0`). Set `1` behind a TLS-terminating proxy so its `X-Forwarded-Proto` / `X-Forwarded-For` are trusted; otherwise the HTTPS redirect loops and throttling keys on the proxy's address |
| `CONN_MAX_AGE` | seconds a database connection is reused across requests (default `60`; `0` under `DEBUG`) |
| `WEB_CONCURRENCY` | gunicorn worker count in the container (default `3`) |
| `LOG_LEVEL` | default `INFO` |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | largest request body the API accepts, in bytes (default `262144`). Answers and captured emails are small; definitions and themes are read from files, never uploaded |
| `VITE_API_TIMEOUT_MS` | runner build-time variable (set when running `npm run build`): per-request deadline in milliseconds before a save is retried and then reported (default `20000`) |
| `PROLOG_RUNNER_DIST` | directory of the built runner served at the site root (default `frontend/dist` in the checkout; the image bakes it in). Bare-host installs only |

Put TLS termination and HTTP→HTTPS in front (Caddy, nginx, a cloud load
balancer). When `DEBUG=false` the app sends HSTS, secure cookies, nosniff
and a strict referrer policy. A Content-Security-Policy is best set at the
proxy; allow `fonts.googleapis.com`/`fonts.gstatic.com` only if a theme
uses `google_fonts`.

## Privacy defaults

- No raw IP addresses or user agents are stored anywhere: the throttle keys
  in the cache and `user_agent_hash` on a response are salted SHA-256
  hashes (`PROLOG_CLIENT_KEY_SALT`, `SECRET_KEY` by default).
- Contact-capture emails live in `SurveyContact` with no reference to any
  response and are exported separately.
- No third-party analytics; the only browser storage is the response id
  used to resume.

## Operations

| Task | Command |
| --- | --- |
| Health / readiness | `GET /api/health/` → `{"status": "ok", "checks": {"database", "active_surveys", "themes"}}` (503 when degraded) |
| Export responses | `manage.py export_responses <slug> [--survey-version X] [--out file.csv] [--include-in-progress]` |
| Export contacts | `manage.py export_contacts <slug> [--survey-version X] [--out file.csv]` |
| Purge abandoned responses | `manage.py purge_abandoned_responses [--days N] [--dry-run]` — schedule daily (`--days` must be at least 1) |
| Send due invitations | `manage.py send_due_invitations` — schedule daily (RUN-5): creates the administrations due today and emails their links; needs `EMAIL_BACKEND`/`PROLOG_EMAIL_FROM` and a real `PROLOG_PUBLIC_URL`. One run at a time (a second concurrent run exits with a notice). Schedule semantics in [integration.md](integration.md) |
| Reload definitions | `manage.py load_definitions` (drafts; exits non-zero when a file is skipped) or `load_definition <file> --activate` |
| Reload themes | restart the app (themes are registered at first use) |

### Backups

Back up PostgreSQL nightly (`pg_dump -Fc prolog > prolog-$(date +%F).dump`)
and keep the customer repository (definitions + themes) under version
control; together they are a complete restore. Restore drill: create an
empty database, `pg_restore`, start the app, open a submitted response in
the admin, run an export.

### Upgrading PROlog

1. Bump the image tag.
2. `validate_definition` every definition against the new schema version;
   `register_theme` every theme.
3. Deploy; the container migrates on start.
4. Smoke test.

### Migrations are append-only

From the first release tag on, a shipped migration is never edited or
deleted — a database that already applied it would report "no migrations
to apply" while its tables no longer match the models. Schema changes add
a new migration; CI (`scripts/check_migrations_append_only.sh`) fails a
pull request that rewrites a released one. Before the first tag migrations
may still be reshaped: recreate any pre-release database when they change
(`dropdb prolog && createdb prolog && manage.py migrate`).

`0001_initial` adds the participant columns only when
`PROLOG_PARTICIPANT_MODEL` is set (integrated profile). A database migrated
in the standalone profile and later switched to integrated records that
migration as applied without the columns; `migrate` (and `manage.py check
--database default`) then fails with `prolog_surveys.E002` and the remedy:
`manage.py migrate prolog_surveys zero --fake --skip-checks`, then
`manage.py migrate`.

## Local development

```sh
cd backend && uv sync && createdb prolog && uv run python manage.py migrate
uv run python manage.py load_definition ../examples/sample-wellbeing.json --activate
uv run python manage.py runserver 8000
cd ../frontend && npm ci && npm run dev      # http://localhost:5173/s/sample-wellbeing
```

Running PostgreSQL from the compose file instead (`docker compose up -d`,
the `db` service alone) needs `POSTGRES_PASSWORD` set in `.env`, and
exported in the shell for `pytest` and `manage.py` to reach it.

Tests: `uv run pytest` (backend, needs PostgreSQL), `npm test` (frontend
units + shared engine vectors), `npm run e2e` (Playwright against a real
backend on ports 8765/5199; `npm run e2e:install` once for Chromium).
`make docker` builds the deployment image locally; CI builds and smoke-tests
it on every pull request (`docker` job).
