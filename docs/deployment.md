# Deploying PROlog (standalone profile)

**Requirements:** DEP-1…DEP-6, NFR-1, NFR-5 in [requirements.md](requirements.md). For the integrated profile (inside PRomop) see [implementation-plan.md](implementation-plan.md) Phase 7.

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
cp .env.example .env            # set SECRET_KEY, ALLOWED_HOSTS, CORS, public URL, data dir
docker compose --profile app up -d --build
docker compose exec app python manage.py load_definition /data/surveys --activate
open http://localhost:8000/s/<slug>
```

The container runs `migrate` and `load_definitions` (drafts) at start; a
survey goes live only when a version is activated explicitly.

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
| `POSTGRES_*` | database connection (no SQLite fallback) |
| `PROLOG_PROFILE` | `standalone` (default) or `integrated` |
| `PROLOG_DEFINITION_DIRS`, `PROLOG_THEME_DIRS` | path-separated directory lists |
| `PROLOG_THROTTLE_CREATE/ANSWER/READ` | throttle rates (`30/hour`, `600/hour`, `1200/hour`) |
| `PROLOG_ABANDONED_RESPONSE_DAYS` | retention of in-progress responses (default 90) |
| `PROLOG_CLIENT_KEY_SALT` | salt for hashed client keys (throttling); rotate to reset |
| `EMAIL_BACKEND`, `PROLOG_EMAIL_FROM` | invitations (integrated profile) |
| `SECURE_SSL_REDIRECT` | `true` by default when `DEBUG=false`; `/api/health/` is exempt |
| `PROLOG_NUM_PROXIES` | number of reverse proxies in front of the app (default `0`). Set `1` behind a TLS-terminating proxy so its `X-Forwarded-Proto` / `X-Forwarded-For` are trusted; otherwise the HTTPS redirect loops and throttling keys on the proxy's address |
| `LOG_LEVEL` | default `INFO` |

Put TLS termination and HTTP→HTTPS in front (Caddy, nginx, a cloud load
balancer). When `DEBUG=false` the app sends HSTS, secure cookies, nosniff
and a strict referrer policy. A Content-Security-Policy is best set at the
proxy; allow `fonts.googleapis.com`/`fonts.gstatic.com` only if a theme
uses `google_fonts`.

## Privacy defaults

- No IP addresses or user agents are stored; throttling uses salted hashes.
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
| Purge abandoned responses | `manage.py purge_abandoned_responses [--days N] [--dry-run]` — schedule daily |
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

## Local development

```sh
cd backend && uv sync && createdb prolog && uv run python manage.py migrate
uv run python manage.py load_definition ../examples/sample-wellbeing.json --activate
uv run python manage.py runserver 8000
cd ../frontend && npm ci && npm run dev      # http://localhost:5173/s/sample-wellbeing
```

Tests: `uv run pytest` (backend, needs PostgreSQL), `npm test` (frontend
units + shared engine vectors), `npm run e2e` (Playwright against a real
backend on ports 8765/5199; `npm run e2e:install` once for Chromium).
