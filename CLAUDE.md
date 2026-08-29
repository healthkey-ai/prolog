# PROlog

Generic, customer-agnostic survey platform for patient-reported outcomes: a
participant **runner** driven by a declarative survey definition (JSON), themed
per deployment, deployable standalone or inside PRomop. A **designer** comes
last. This repository is **public**.

## Source-of-truth documents (read before product/design decisions)

- `docs/requirements.md` — numbered requirements (DEP/DEF/RUN/Q/CON/THM/NFR ids)
- `docs/implementation-plan.md` — phases, stack, layout, testing strategy
- `schema/survey-definition.schema.json` — the survey definition contract
- `schema/theme.schema.json` — the runner theme contract; `themes/default/` is the neutral theme

## Hard rules

- **Customer-agnostic.** Never use a specific customer's name, brand, domain,
  instrument title, question wording, colours, or fonts in code, tests,
  fixtures, docs, commit messages, or PR text. Customer content lives in that
  customer's private repository and is mounted at deployment
  (`PROLOG_DEFINITION_DIRS`, `PROLOG_THEME_DIRS`). Describe customer needs as
  neutral capabilities; use `examples/` for neutral sample instruments and
  `themes/default` for styling. A CI deny-list guard enforces this.
- **Survey content is data, not code.** Question/option text never appears in
  backend or frontend code; it comes from a definition file validated against
  `schema/survey-definition.schema.json`. Published versions are immutable;
  wording/structure changes are a new `version`.
- **A survey is a DAG.** `visible_if` and `rows_from` are directed edges and
  may only point to *earlier* questions in presentation order (DEF-10). Never
  add a schema feature or engine shortcut that allows forward references or
  cycles; visibility is one forward pass, and cascade invalidation walks the
  DAG forward from the changed answer.
- **Server is authoritative.** Visibility, limits, exclusives, cascade
  invalidation and completion are validated server-side; the client mirrors
  them for UX only. Shared test vectors keep the Python and TypeScript engines
  in lockstep.
- **Tokens, not colours.** Components reference CSS variables from
  `styles/tokens.css` only; brand values come from a theme at runtime. No hex
  colours in components.
- **No PII in anonymous flows.** No IP addresses or emails on responses, in
  logs, exports, or telemetry. Contact capture is stored unlinked; identity
  capture goes only to the configured identity service.
- **Runner first, designer last.** Do not start designer work before the
  runner phases in the plan are complete.

## Branching and merging

- `dev` is the default working branch; `main` is release-ready.
- **No direct commits or pushes to `dev` or `main`** — both are protected.
  All changes go through a pull request from a feature branch
  (`feat/…`, `fix/…`, `docs/…`) into `dev`; releases are PRs from `dev` into
  `main`. Never force-push or bypass the rules.
- Branch from `dev`. Keep PRs scoped to one phase item; CI must be green.
- Merged feature branches are deleted automatically on GitHub
  (`delete_branch_on_merge`); after a merge run `git fetch --prune` and
  delete the local branch. Don't reuse a merged branch name.
- Git identity: vtrv101 <vtrv101@gmail.com>.

## Stack & tooling

Always the latest stable releases — check the registry when scaffolding or
adding a dependency rather than trusting these numbers (checked 2026-08-29):
Python 3.13+ / Django 6.1 / DRF 3.18 / psycopg 3.3 / PostgreSQL 18;
Node 24 LTS (≥ 22) / Vite 8 / React 19 / TypeScript 7 / Tailwind CSS 4 /
shadcn / TanStack React Query 5 / React Router 8 / i18next / Vitest /
Playwright.

- Backend deps: `uv` with `backend/pyproject.toml` (Phase 0 replaces
  `requirements.txt`). Frontend: npm in `frontend/`.
- Local Postgres via `docker-compose up -d` (postgres:18). No SQLite, ever.
- Validate a definition: `python -m jsonschema -i <file> schema/survey-definition.schema.json`
  (or `manage.py validate_definition <file>` once Phase 1 lands).

## Conventions

- Backend app is `prolog_surveys`; pure engine logic in `prolog_surveys/engine/`
  has no Django imports.
- Frontend: TanStack Query owns server state (no Redux); navigation/visibility
  logic in pure, unit-tested functions under `frontend/src/survey/`.
- WCAG 2.2 AA: real `fieldset`/`legend`, ≥44 px targets, `:focus-visible`
  rings, `prefers-reduced-motion`.
- All runner chrome strings go through i18next (`frontend/src/i18n/`).
