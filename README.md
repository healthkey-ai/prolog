# PROlog

PROlog is a survey designer and runner for patient-reported outcomes. Its Django
application is intended to run alongside **PRomop**; React provides the designer
and participant experience.

The evolving product requirements are in [docs/requirements.md](docs/requirements.md).

## Layout

- `backend/` — Django project and reusable survey app.
- `frontend/` — React/Vite interface.
- `docs/` — requirements and integration decisions.

The backend intentionally has no SQLite fallback. Configure it to use the PRomop
database, and install its app in the PRomop Django project before migrating.
