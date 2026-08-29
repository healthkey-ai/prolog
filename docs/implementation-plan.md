# PROlog implementation plan

**Status:** proposed  
**Updated:** 2026-08-29  
**Requirements:** [requirements.md](requirements.md) (IDs referenced below)  
**Contracts:** [schema/survey-definition.schema.json](../schema/survey-definition.schema.json) · [schema/theme.schema.json](../schema/theme.schema.json) · [themes/default/theme.json](../themes/default/theme.json)

## 1. Goal and shape of the work

Ship a brand-neutral **survey runner** that executes any survey definition
conforming to the schema in this repository, themed per customer at runtime,
deployable standalone (own PostgreSQL) or inside PRomop. The first customer
instrument is maintained in a private repository and is run by mounting its
definition and theme into a PROlog deployment; nothing customer-specific is
committed here.

The **designer/editor is the last phase**. Until it ships, survey authors edit
definition JSON files, validate them with the CLI, and load them with a
management command. Every runner feature is built against the JSON contract
so the designer later becomes an editor over that contract rather than a
second model.

Order of phases (each is independently mergeable to `dev`):

| Phase | Deliverable | Requirement IDs |
| --- | --- | --- |
| 0 | Neutral scaffold, stack pins, deployment profiles, CI | DEP-1…6 |
| 1 | Definition schema, semantic validation, loader, versioning | DEF-1…9 |
| 2 | Response engine API | RUN-1…5, RUN-14…19, Q-1…12, CON-3, CON-5, CON-6 |
| 3 | Runner core UI | RUN-6…13, THM-4 (token plumbing only) |
| 4 | Complex question types | Q-4, Q-6, Q-7, RUN-16 |
| 5 | Theming | THM-1…8 |
| 6 | i18n, accessibility, export, hardening → first standalone launch | DEF-5, NFR-1…8 |
| 7 | Integrated profile: participant link, identity capture, consent, repeat administration | DEP-2, CON-1, CON-2, CON-4, RUN-5 |
| 8 | Designer and preview | Designer section |
| 9 | Mapping review, concept search, OMOP write-back | Mapping section |

## 2. Stack

Always the latest stable release at the time of scaffolding; the versions
below were checked against the registries on 2026-08-29 and are the minimum
pins. Re-check before installing.

| Layer | Package | Version |
| --- | --- | --- |
| Backend | Python | 3.13+ |
| | Django | 6.1 |
| | Django REST Framework | 3.18 |
| | psycopg | 3.3 |
| | django-cors-headers | 4.9 |
| | jsonschema | 4.26 |
| | PostgreSQL | 18 |
| Frontend | Node | 24 LTS (≥ 22) |
| | Vite | 8.2 |
| | React / React DOM | 19.2 |
| | TypeScript | 7.0 |
| | Tailwind CSS (+ `@tailwindcss/vite`) | 4.3 |
| | shadcn (CLI) / Radix primitives | 4.19 |
| | TanStack React Query | 5.102 |
| | React Router | 8.3 |
| | i18next / react-i18next | 26 / 17 |
| | @dnd-kit/sortable | 10 |
| | Vitest, Playwright | latest |

Tooling: `uv` with `backend/pyproject.toml` (replace `requirements.txt`),
npm workspace in `frontend/`, `docker-compose.yml` with `postgres:18`,
GitHub Actions for lint/typecheck/test on every PR.

## 3. Target repository layout

```
prolog/
├── schema/
│   ├── survey-definition.schema.json   # DEF-1 contract (done)
│   └── theme.schema.json               # THM-1 contract (done)
├── themes/default/theme.json           # neutral theme (done)
├── examples/                           # neutral sample definitions used by tests and demos
│   └── sample-wellbeing.json
├── backend/
│   ├── pyproject.toml
│   ├── manage.py
│   ├── prolog/                         # standalone project: settings.py, urls.py, asgi/wsgi
│   └── prolog_surveys/                 # reusable app (renamed from `surveys`)
│       ├── apps.py
│       ├── conf.py                     # PROLOG_* settings with defaults
│       ├── models.py
│       ├── migrations/
│       ├── definitions/                # schema loading, semantic validation, normalisation
│       │   ├── schema.py
│       │   ├── validate.py
│       │   └── loader.py
│       ├── engine/                     # pure domain logic, no Django imports
│       │   ├── visibility.py           # visible questions, condition evaluation
│       │   ├── answers.py              # per-type answer validation
│       │   ├── cascade.py              # invalidation on gate change
│       │   └── completion.py
│       ├── themes/                     # registry, validation, contrast check
│       ├── options/                    # built-in option sources (ISO 3166)
│       ├── api/                        # DRF serializers, views, throttles, urls
│       ├── management/commands/        # validate_definition, load_definition, export_responses, register_theme
│       ├── admin.py
│       └── tests/
├── frontend/
│   ├── package.json
│   └── src/
│       ├── api/                        # typed client + React Query hooks
│       ├── survey/                     # pure functions: navigation, visibility, answer shapes (mirrors engine/)
│       ├── components/                 # shadcn base + question renderers
│       ├── pages/                      # Intro, Wizard, Complete
│       ├── theme/                      # theme loader → CSS variables, font faces
│       ├── i18n/                       # runner chrome strings en (+ customer languages via theme.strings)
│       └── styles/tokens.css           # token names only; values come from the theme
├── docker/                             # Dockerfile (backend + built runner), compose
├── docs/
└── CLAUDE.md
```

## 4. Phases

### Phase 0 — Neutral scaffold and deployment profiles

Goal: a clean, brand-free, correctly-pinned skeleton that runs standalone.

- Remove all customer references from the scaffold (`frontend/src/main.tsx`
  currently contains a named customer instrument; replace with a neutral
  placeholder). Add a CI grep guard that fails on a configurable deny-list of
  customer names.
- Rename the app to `prolog_surveys` (label `prolog_surveys`) so it installs
  cleanly inside PRomop without clashing.
- Move to `pyproject.toml`/`uv`; pin the stack from §2; add
  `docker-compose.yml` (postgres:18) and a `Dockerfile` that builds the runner
  and serves it from Django (`whitenoise`) so one image is a full standalone
  deployment (DEP-5).
- `conf.py`: `PROLOG_PROFILE = "standalone" | "integrated"`,
  `PROLOG_PARTICIPANT_MODEL` (default `None`), `PROLOG_DEFINITION_DIRS`,
  `PROLOG_THEME_DIRS`, `PROLOG_IDENTITY_SERVICE` (dotted path), throttling
  rates.
- Participant FK: `SurveyResponse.participant` is created only when
  `PROLOG_PARTICIPANT_MODEL` is set (pattern: `settings.AUTH_USER_MODEL`-style
  string resolved at model definition time); migrations for the standalone
  profile omit it. Integrated migrations are generated inside PRomop (DEP-2).
- Frontend scaffold: Vite 8 + React 19 + TS 7 + Tailwind 4 (`@tailwindcss/vite`)
  + shadcn init + React Query + React Router + i18next. Strict TS, ESLint,
  Prettier, Vitest.
- GitHub Actions: backend (ruff, mypy, pytest with Postgres service),
  frontend (tsc, eslint, vitest), schema validation of `examples/*.json` and
  `themes/*/theme.json`.

Acceptance: `docker compose up` serves the placeholder runner at `/` and
`/api/health/`; CI green; no customer names in the repository.

### Phase 1 — Definition schema, validation, loader

Goal: the JSON contract is enforced and stored immutably (DEF-1…9).

- `definitions/schema.py`: load `schema/survey-definition.schema.json` once;
  `validate_schema(doc)` with jsonschema 2020-12.
- `definitions/validate.py`: semantic rules (DEF-6) returning structured
  errors with JSON paths. Rules: unique section/question/option keys;
  `visible_if.question`, `rows_from` reference an earlier question of a
  compatible type; conditions use `value`/`values` that exist on the referenced
  question's options; no cycles; `max_selections`/`min_selections` bounds;
  `optional_items` ⊆ option keys; ≤ 1 `email` question; `link_identity`
  requires integrated profile; `translation_status` present for every
  non-default language; every i18n object has the default language.
- `definitions/loader.py`: normalise (stable key order, defaults filled) →
  `SurveyVersion.definition`; `Survey` upsert by `slug`; version upsert by
  (`slug`, `version`) only while `draft`; activation archives the previous
  active version; refuse activation while any language is `machine` (DEF-5).
- Management commands `validate_definition <file>` and
  `load_definition <file> [--activate]`; startup hook loads
  `PROLOG_DEFINITION_DIRS` in `draft` state (activation stays explicit).
- Materialise `SurveyQuestion`/`SurveyOption` projections on activation.
- `examples/sample-wellbeing.json`: a neutral instrument exercising every
  question type, both branch directions, a dynamic matrix, a ranking with an
  optional item, limits and exclusives, contact capture, three languages
  (one `machine`). This file is the fixture for all later tests.

Acceptance: every DEF-6 rule has a failing fixture and test; the example
loads, activates, and its stored definition equals the normalised file.

### Phase 2 — Response engine API

Goal: complete server-side runner semantics, testable without a UI.

- Models: `SurveyResponse` (UUID pk = capability token, `language`,
  `status`, `started_at`, `submitted_at`, `last_question_key`,
  `user_agent_hash`), `SurveyAnswer` (`response`, `question_key`, `value`
  JSON, `option_keys` array for indexing, `updated_at`, unique per
  response/question), `SurveyContact` (no response FK), `SurveyConsent`.
- `engine/visibility.py`: `visible_questions(definition, answers)` —
  evaluates `visible_if` on sections and questions with ops `eq`, `neq`,
  `in`, `contains`, `answered` (a skipped answer counts as not answered).
- `engine/answers.py`: per-type validators producing the canonical shapes in
  Q-1…Q-12; matrix validation checks rows against the current `rows_from`
  selection.
- `engine/cascade.py`: after an upsert, recompute visibility; delete answers
  of now-hidden questions; prune matrix ratings whose rows disappeared;
  return `invalidated`.
- `engine/completion.py`: missing keys = visible questions without an answer
  row (value or skip).
- API (`/api/run/…`, RUN table in requirements): definition (localized, ETag,
  `notes` stripped), options source (ISO 3166 localized via `pycountry`),
  create response, get response, upsert answer, submit, contact. Completed
  responses are read-only (409 on write).
- Throttling per response id and per hashed client key; CORS from settings;
  no IP persisted anywhere (CON-6).
- Admin: read-only response browser with answer inline and completion stats.

Acceptance: API tests cover every question type's valid and invalid shapes,
both branch gates opening and closing (including matrix pruning), skip
handling, completion with missing keys, read-only after submit, contact
capture storing nothing on the response.

### Phase 3 — Runner core UI

Goal: a usable end-to-end wizard with the simple question types, using only
design tokens (no brand values).

- `styles/tokens.css` declares every CSS variable the components use
  (`--p-primary`, `--p-primary-deep`, `--p-on-primary`, `--p-secondary`,
  `--p-accent`, `--p-focus`, `--p-ground`, `--p-surface`, `--p-tint`,
  `--p-ink`, `--p-ink-soft`, `--p-line`, `--p-error`, `--p-success`,
  `--p-radius-card|input|button|sheet`, `--p-font-heading|body`,
  `--p-tracking`, `--p-shadow`, `--p-content-max`). Tailwind 4 `@theme`
  maps utilities to these variables. The default theme's values are the
  hard-coded fallbacks.
- `survey/navigation.ts` + `survey/visibility.ts`: pure, unit-tested mirrors
  of the backend engine (same fixture, same expected outputs — a shared JSON
  test-vector file under `examples/vectors/` keeps them in lockstep).
- Pages: Intro (title, intro copy, estimated time, anonymity note, language
  cards, consent block if defined, Start / Continue / Start again with
  confirm), Wizard (`/s/:slug/q/:key`), Complete (completion copy, contact
  step if last question is contact capture).
- Wizard shell: sticky header (logo slot, section label, overview button),
  progress bar over visible questions, question area (eyebrow "Question n of
  m", text, help, control), sticky footer (Back · saved indicator · Next /
  Finish). Section interstitials when enabled.
- Renderers: `single` (radio cards + inline other), `dropdown` (combobox with
  options source), `scale` (segmented buttons + labels), `text`, `number`,
  `date`, `info`, `email` (input + help panel + equal-weight Skip).
- Autosave via React Query mutation with optimistic update, backoff retry,
  `invalidated` pruning; saved indicator; block Next only on final failure.
- Skip policy UX: inline "Skip this question?" confirmation for `soft`;
  disabled Next for `hard`; silent for `none`/`required=false`.
- Resume: response id in `localStorage` keyed by slug; Continue/Start again.
- Overview panel: `Sheet` on mobile, side panel ≥1024 px; rows with status
  glyph and answer summary; navigable when answered or reachable.

Acceptance: Playwright happy path on the example definition through every
simple type; unit tests for navigation with branches opening/closing; axe
scan clean on every screen.

### Phase 4 — Complex question types

- `multi`: checkbox cards, `max_selections` counter and inert state at the
  limit, `min_selections`, exclusive options auto-clearing with a short
  settle animation, inline other text.
- `ranking`: dnd-kit sortable list with drag handle **and** ▲▼ buttons,
  `aria-live` position announcements, `optional_items` left unranked unless
  the participant adds text/opts in.
- `matrix`: rows from `rows` or from the current `rows_from` selection
  (labelled with the participant's own "other" text where applicable), one
  segmented scale per row, legend once, vertical stacking at all widths.
- Cascade UX: when a gate changes mid-survey, the overview and progress update
  and the server's `invalidated` list prunes the cache; Next resumes forward
  through the recomputed visible list.

Acceptance: Playwright covers limits, exclusives, ranking by keyboard, matrix
rows following the source selection, and both gate directions.

### Phase 5 — Theming

Goal: THM-1…8; a customer theme mounted at deploy time restyles the runner
with no rebuild.

- Backend `themes/registry.py`: scan `PROLOG_THEME_DIRS` at startup, validate
  each `theme.json` against the theme schema, run the contrast check (THM-8),
  register; `register_theme <dir>` command for one-off validation.
- API: `GET /api/run/themes/{code}/` (theme JSON with asset paths rewritten
  to absolute URLs) and `/assets/{path}` (whitelisted extensions, immutable
  cache headers, path-traversal safe).
- Survey → theme: `Survey.theme_code` from the definition's `theme`; the
  definition endpoint returns `theme_code`; unknown codes fall back to
  `default` with a logged warning (THM-3).
- Frontend `theme/applyTheme.ts`: fetch theme before first paint (or inline
  in the HTML shell via a server-rendered `<script type="application/json">`
  to avoid a flash), set CSS variables on `:root`, inject `@font-face` rules
  from `font_faces`, optionally load `google_fonts`, set `data-immersive`,
  `data-align`, `data-logo` attributes for layout switches, merge `strings`
  into i18next resources. `light-dark` themes attach a
  `prefers-color-scheme` media block for the `dark` palette.
- Decorative assets: immersive intro/completion screens render `decor` SVGs
  `aria-hidden`, positioned by the layout, never behind body copy.
- Ship a second built-in theme, `themes/contrast` (high-contrast, larger
  type), to prove the mechanism with a non-default theme and as an
  accessibility option.
- Docs: `docs/theming.md` — how a customer authors a theme directory, hosts
  licensed fonts, and mounts it; a checklist of contrast and text-size rules.

Acceptance: a test theme with a distinct palette and a self-hosted font
renders in Playwright with the expected computed styles; an invalid theme is
rejected at registration; the default theme is used when a survey references
an unknown code.

### Phase 6 — i18n, accessibility, export, hardening → first standalone launch

- Runner chrome strings in i18next for the default language plus the
  languages the first customer needs; theme `strings` overrides; `lang`
  attribute follows the chosen language; text-expansion QA (NFR-6).
- Accessibility audit against NFR-3 on every screen and question type;
  fix list closed before launch.
- `export_responses --format=csv` (NFR-5) and `export_contacts`, separate
  files, never joined.
- Throttling tuned, security headers, dependency audit, backup/restore
  runbook, monitoring hooks (health, metrics), retention job for abandoned
  in-progress responses.
- Performance pass (NFR-7): definition/theme ETags, code-splitting the
  ranking/matrix renderers, font `display: swap`.
- Release: tag `v0.1.0`; container image published; `docs/deployment.md`
  describes composing a customer deployment (image + definition dir + theme
  dir + env) and the promotion flow (draft → validate → activate).

### Phase 7 — Integrated profile

- `PROLOG_PARTICIPANT_MODEL` wired to PRomop `omop_core.Person`; migrations
  generated inside PRomop; `account` resume mode.
- Identity capture (CON-4): `POST …/identity/` calls
  `PROLOG_IDENTITY_SERVICE` with an idempotency key derived from the response
  id; links `participant`, sets `identity_linked_at`; never persists the
  email; failure leaves the response anonymous.
- Consent attestation and re-consent (CON-1, CON-2).
- Invitations and repeat administration (RUN-5): `SurveyInvitation`,
  `SurveyAdministration`, scheduler command, email templates (themeable).

### Phase 8 — Designer and preview

- React designer over the definition schema: survey metadata, sections,
  questions, options, per-type config, visibility rules with cycle and
  reachability checks (DEF-6 surfaced live), translations with review
  status, theme selection, consent, participation/presentation settings.
- Draft/review/approve/publish/pause/retire lifecycle with organisation-scoped
  permissions; publishing produces exactly the same `SurveyVersion.definition`
  the loader would; import/export of the JSON file round-trips.
- Non-persisting preview renders the runner against an unsaved draft (runner
  accepts a signed, short-lived preview definition).
- Designer API: `GET/POST /api/surveys/`, `GET/PATCH /api/surveys/{id}/draft/`,
  `POST /api/survey-versions/{id}/preview/`, `/publish/`.

### Phase 9 — Mapping and OMOP write-back

- `ConceptMapping` authoring against `SurveyQuestion`/`SurveyOption`
  projections; concept search against PRomop vocabularies; ECOG/Karnofsky
  mapping assistant with reviewable suggestions; approval workflow.
- `MappingExecution` after submission (idempotent), writing to `observation`,
  `note`, `note_nlp` through PRomop's write path with full provenance; states
  success / no-result / error / superseded; raw answers untouched.

## 5. How a private customer repository uses the runner

A customer repository contains only content and configuration:

```
customer-survey/
├── surveys/<slug>.json        # definition, validated against prolog/schema at the pinned version
├── theme/<code>/theme.json    # + logo, decor SVGs, licensed font files
├── deploy/                    # compose/helm values: image tag, env, mounted dirs, domain
└── docs/                      # the customer's own requirements, sign-offs, translations log
```

Deployment composes the published PROlog image with those two directories
mounted at `PROLOG_DEFINITION_DIRS` and `PROLOG_THEME_DIRS`. The customer
pins a PROlog release tag; upgrading is a tag bump plus re-validation of the
definition against the new schema version. Nothing in the customer repository
is required to build PROlog, and nothing in PROlog references the customer.

## 6. Testing strategy

- Shared JSON test vectors (`examples/vectors/*.json`): definition + answer
  sequence → expected visible list, invalidated keys, completion result. Both
  the Python engine and the TypeScript `survey/` module run the same vectors.
- Backend: pytest with a Postgres service; factories for definitions;
  property-based tests for answer validators.
- Frontend: Vitest for pure modules and renderers; Playwright for flows;
  axe-core in Playwright for accessibility.
- Contract: the API's definition payload is snapshot-tested against the
  schema so the frontend types (generated from the schema with
  `json-schema-to-typescript`) stay in sync.

## 7. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Engine logic drifts between Python and TypeScript | Shared test vectors (§6); server is authoritative, client is UX only. |
| Theme values leak into components | Components import token names only; CI greps for hex colours outside `themes/` and `tokens.css` fallbacks. |
| Customer content leaks into the public repository | CI deny-list guard (Phase 0); PR template checklist item. |
| Integrated-profile migrations diverge from standalone | Single models module; profile-specific fields guarded by settings; migration tests run in both profiles in CI. |
| Licensed fonts | Theme schema supports self-hosted faces from the mounted theme directory; nothing licensed enters PROlog. |
| Designer built on a different model than the runner | Designer is deferred and specified as an editor over the same JSON contract (Phase 8). |
