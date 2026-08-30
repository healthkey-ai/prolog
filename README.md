# PROlog

PROlog is a generic, customer-agnostic survey platform for patient-reported
outcomes. Its **runner** executes any survey described by the declarative
definition in [`schema/survey-definition.schema.json`](schema/survey-definition.schema.json),
styled by a runtime **theme** ([`schema/theme.schema.json`](schema/theme.schema.json)),
and runs either standalone against its own PostgreSQL database or installed as
a Django app inside **PRomop**. A **designer** for authoring instruments is the
final phase.

- Requirements: [docs/requirements.md](docs/requirements.md)
- Implementation plan: [docs/implementation-plan.md](docs/implementation-plan.md)
- Deployment and operations: [docs/deployment.md](docs/deployment.md)
- Theming: [docs/theming.md](docs/theming.md)
- Working agreements: [CLAUDE.md](CLAUDE.md)

## Quick start

```sh
cd backend && uv sync && createdb prolog && uv run python manage.py migrate
uv run python manage.py load_definition ../examples/sample-wellbeing.json --activate
uv run python manage.py runserver 8000
cd ../frontend && npm ci && npm run dev        # open http://localhost:5173/s/sample-wellbeing
```

Tests: `uv run pytest` · `npm test` · `npm run e2e` (see docs/deployment.md).

## Layout

- `schema/` — survey definition and theme contracts (JSON Schema 2020-12).
- `themes/` — built-in themes (`default`, `contrast`).
- `examples/` — neutral sample instrument and the shared engine test vectors.
- `backend/` — Django project and the reusable `prolog_surveys` app.
- `frontend/` — React/Vite runner (designer later).
- `docs/` — requirements, plan, integration decisions.

Customer instruments and brand themes are **not** part of this repository.
A customer repository holds its definition JSON and theme directory and mounts
them into a PROlog deployment (`PROLOG_DEFINITION_DIRS`, `PROLOG_THEME_DIRS`);
see the plan, §5.

## Python tooling

The backend uses [`uv`](https://docs.astral.sh/uv/) with `backend/pyproject.toml`
and a committed `uv.lock` instead of `venv` + `pip`. The main reason is CI
speed: `uv sync` installs a locked environment roughly 10–100× faster than
`pip install`, which keeps every pull-request build short. The lockfile also
gives identical installs across developer machines, CI, and the container
image. `pyproject.toml` remains tool-agnostic, so `pip install -e backend/`
still works if needed.

## Branches

`dev` is the default working branch; `main` is release-ready. Both are
protected: changes land only via pull requests.

## Database

There is no SQLite fallback. Standalone deployments use their own PostgreSQL
database; integrated deployments use PRomop's database and apply migrations
from the PRomop project.
