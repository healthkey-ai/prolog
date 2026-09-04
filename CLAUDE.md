# PROlog

Generic, customer-agnostic survey platform for patient-reported outcomes: a
participant **runner** driven by a declarative survey definition (JSON), themed
per deployment, installed as a Django app inside **PRomop**, which owns the
database (revision 2026-08-31 — there is no PROlog datastore). A **designer**
comes last. This repository is **public**.

## Source-of-truth documents (read before product/design decisions)

- `docs/requirements.md` — numbered requirements (DEP/DEF/RUN/Q/CON/THM/NFR ids)
- `docs/implementation-plan.md` — phases, stack, layout, testing strategy
- `docs/promop-migration-plan.md` — how the backend moves into PRomop (M0–M4), and the proposed RUN-2 primitive
- `schema/survey-definition.schema.json` — the survey definition contract
- `schema/theme.schema.json` — the runner theme contract; `themes/default/` is the neutral theme
- `docs/definitions/survey-definition.md`, `docs/definitions/theme-definition.md` — field-by-field manuals for both contracts
- `docs/administration.md` — the administrator's manual: how surveys work, and how to publish one

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
  logs, exports, or telemetry. Identity capture (the default) sends the address
  only to the host's identity service, which creates the account for the person
  the response is already bound to; PROlog never persists the address. Contact
  capture (`store_separately`) remains for mailing-list-only instruments.
- **Every response has a person.** A response is always bound to a PRomop
  `Person` (DEP-2, RUN-2); "anonymous" means that person carries nothing that
  could name them, not that no record exists. Never add a path that creates a
  response without one.
- **Don't call an instrument anonymous on the deployment's behalf.** The runner
  renders the anonymity statement the definition supplies; an instrument that
  creates accounts from an email is not anonymous for those participants and
  its copy must say so (CON-8).
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

**The backend follows PRomop's pins**, because it runs in PRomop's process:
Django 5.2.6 / DRF 3.15.2 / django-cors-headers 4.4.0 / whitenoise 6.7.0 /
psycopg 3.3 / PostgreSQL 18, on Python 3.13+. Bumping any of them is a PRomop
decision, not this repository's. The port off Django 6.1 is M0 in
`docs/promop-migration-plan.md`; until it lands the code still builds against
6.1 and the only incompatible API is the multi-backend mail interface.

The front end keeps its own stack at the latest stable releases — it is built,
not imported, and shares no runtime with PRomop (checked 2026-08-29):
Node 24 LTS (≥ 22) / Vite 8 / React 19 / TypeScript 7 / Tailwind CSS 4 /
shadcn / TanStack React Query 5 / React Router 8 / i18next / Vitest /
Playwright.

- Backend deps: `uv` with `backend/pyproject.toml` (no `requirements.txt`).
  Frontend: npm in `frontend/`.
- Local Postgres via `docker-compose up -d` (postgres:18). No SQLite, ever.
- Validate a definition: `python -m jsonschema -i <file> schema/survey-definition.schema.json`
  or `manage.py validate_definition <file>` (schema + semantic rules).

## Conventions

- Backend app is `prolog_surveys`; pure engine logic in `prolog_surveys/engine/`
  has no Django imports.
- Frontend: TanStack Query owns server state (no Redux); navigation/visibility
  logic in pure, unit-tested functions under `frontend/src/survey/`.
- WCAG 2.2 AA: real `fieldset`/`legend`, ≥44 px targets, `:focus-visible`
  rings, `prefers-reduced-motion`.
- All runner chrome strings go through i18next (`frontend/src/i18n/`).
- **Migrations are append-only** once a release tag exists: never edit or delete a shipped migration, add a new one (CI runs `scripts/check_migrations_append_only.sh`). Before the first tag, recreate pre-release databases when a migration changes.

## Code review loop

When asked to review and fix a branch/PR "until clean", run the `code-review`
skill (`high --fix <base>...<head>`) from this directory in a loop and:

- **Fix every confirmed finding**, not only the top-10 the skill reports —
  including the cleanup / reuse / simplification / efficiency angles. A pass
  that leaves a "confirmed but below the cap" tail does not converge.
- **Verify before committing**: backend pytest against the app's own harness
  (`PROLOG_PARTICIPANT_MODEL=auth.User` — a test fixture standing in for
  PRomop's `omop_core.Person`, not a deployment profile), ruff, `tsc -b`,
  vitest, Playwright (twice if anything looked flaky). One commit per pass,
  pushed to the PR branch.
- **Convergence**: stop when a pass returns only items already decided below,
  or nothing.
- If a review agent stalls waiting on child verifiers that are not running,
  resume it with a message to verify in-context and continue.

Decisions that reviewers must treat as settled (implement, don't re-report):

| Topic | Decision |
| --- | --- |
| `presentation.mode: "section"` | Not implemented in this release; the validator rejects it, docs mark it planned. |
| Invitation schedules | Never back-fill past due dates; an invitation with no administrations gets the current cycle only. |
| Throttle cache | Optional shared cache via `CACHE_URL` (Redis / memcached); LocMem is per process and multiplies limits by worker count (documented). |
| Validation messages | Structured error codes (code + params) in both engines and in the API 400 body, mapped to i18n strings in the runner; never match on English text. |
| Neutrality CI guard | Advisory until the `NEUTRALITY_DENYLIST` repository secret exists; enforcing afterwards. Do not re-report. |
| Anonymous surveys and invitations | No invitation link may bind to an anonymous response: `send_pending` skips anonymous surveys and `?invite=` is ignored on them. |
| `DEBUG` | Defaults to `false`; `prolog.settings_dev` (used by `manage.py`/pytest) turns it on locally; the image sets `DEBUG=false` and the placeholder-`SECRET_KEY` guard stays. |
| `--allow-unreviewed` | A review-only activation override that logs loudly; not a bug. |
