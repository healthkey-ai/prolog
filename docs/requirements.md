# PROlog requirements

**Status:** living draft  
**Updated:** 2026-08-31  
**Companion:** [implementation-plan.md](implementation-plan.md) · [schema/survey-definition.schema.json](../schema/survey-definition.schema.json) · [schema/theme.schema.json](../schema/theme.schema.json)

## Changes in this revision (2026-08-31)

PROlog stops being a system of record. **PRomop is the database**; PROlog is the
survey layer over it.

1. **No PROlog database.** PROlog is a Django app installed inside PRomop and
   its tables are created in PRomop's database by PRomop's migrations. There is
   no separate PROlog datastore, no standalone schema, and nothing to migrate or
   reconcile between the two. Surveys, versions, questions, options, responses
   and answers are all PRomop data (DEP-1, DEP-5, Data model).
2. **Every response belongs to a person.** A response is always bound to a
   PRomop `Person`. Where no person is known, PROlog creates one carrying no
   identifying attributes. "Anonymous" therefore means *a person record nobody
   can put a name to*, not *no record at all* (DEP-2, RUN-2, CON-6).
3. **An email creates a patient account.** When a participant supplies an
   address at an email question, the host creates (or finds) an `Identity` and
   `PatientUser` for the `Person` the response is already bound to, promoting
   that person from unidentified to identified in place. The account is the
   point of the question — it is what lets the participant come back, see their
   own data, and be asked less next time (CON-4, CON-7).
4. **Unlinked contact capture is no longer the default answer** to "may we
   email you?". CON-3 remains available for instruments that genuinely want a
   mailing list with no record behind it, but it is now the exception, and a
   deployment must choose it deliberately.
5. **Anonymity statements must be written for what actually happens.** An
   instrument that creates an account from an email is not anonymous for the
   participants who give one, and its intro, consent and privacy copy have to
   say so. This is a documentation requirement on every deployment, not a
   runtime toggle (CON-8).

Superseded: open decisions #1 and #4 below; the standalone profile; the
"first standalone launch" framing of phase 6 in the implementation plan.

## Changes in the 2026-08-29 revision

This revision reorders the product around a **runner-first** delivery and makes
PROlog a neutral, reusable platform that private customer repositories build on.

1. **Runner first, designer last.** The participant runner, driven by a
   file-based survey definition, is the first deliverable. The designer/editor
   is the final phase; until then, instruments are authored as JSON files.
2. **Canonical survey definition schema.** The definition format is now part of
   this repository (`schema/survey-definition.schema.json`). It is the frozen
   snapshot stored on every published version and the contract for the runner.
3. **Two deployment profiles.** *Standalone* (own PostgreSQL, anonymous
   surveys, no clinical integration) and *integrated* (installed in PRomop,
   participant identity and OMOP write-back). The runner must be fully
   functional in standalone mode.
4. **Theming.** The runner supports customer-specific UI themes selected per
   survey, declared in `schema/theme.schema.json`, and mounted at deployment
   without a rebuild of this repository.
5. **Contact capture vs identity capture.** Two distinct optional email steps:
   *contact capture* (address stored separately, never linked to the response)
   and *identity capture* (address sent to the host platform to create/link a
   participant record). A survey uses at most one of them.
6. **Presentation modes and skip policy.** One-question-per-screen wizard with
   an overview/jump-back panel and a soft-required skip policy are first-class,
   configurable behaviours.
7. **Neutrality.** This repository contains no customer content, branding, or
   names. Reference instruments live in private repositories and are described
   here only as capabilities.

## Purpose

PROlog designs, publishes, runs, and analyses participant surveys, with a focus
on patient-reported outcomes. It has two experiences: a **runner** for
participants to complete, save, resume, and submit an instrument, and — later —
a **designer** for authorised staff to compose versioned instruments,
translations, and governed OMOP mappings.

PROlog is a Django/React application installed as an app inside **PRomop**,
which owns the database. PROlog contributes the survey tables to PRomop's
schema, binds every response to a PRomop `Person`, and — where a participant
asks for an account — uses PRomop's identity service to give that person one.
It holds no data of its own and has no datastore that can drift from PRomop's.

## Reference inputs

### Reference instrument (private)

The first instrument to run on PROlog is a multilingual (three languages),
anonymous, seven-section patient-experience survey of roughly 30 questions,
owned by a patient-advocacy organisation and maintained in that organisation's
private repository together with its brand theme. Its wording is the owner's
content and is never reproduced here. The capabilities it requires are:

- Anonymous participation with browser-side resume; no account.
- One question per screen; back to any previously answered question at any
  time; progress and section indicators.
- Controls: searchable country dropdown, single choice, multi-select with
  maximum-selection limits and exclusive options, inline "Other" free text,
  1–5 labelled scales, ranking with optional items, a rating matrix whose rows
  are the options selected in an earlier question, long free text, and an
  optional email step at the end.
- Declarative branching with server-side invalidation of downstream answers
  when a gating answer changes.
- Soft-required skip policy with explicit, analysable skips.
- Machine-translated placeholder languages that must not be published until
  reviewed.
- A strong brand: custom palette, licensed typeface with fallback, decorative
  shapes on intro/completion screens, left-aligned copy, light-only.

Every item above is expressed below as a neutral requirement.

### Prior survey-platform baseline

An existing survey platform establishes useful baseline behaviour:
draft/active/archive lifecycle, multi-step wizard, non-persisting preview,
autosave, started/completed timestamps, completion percentage, and consent
handling. It stores answers in a mutable per-user document. PROlog retains
the UX but uses normalized, versioned, immutable submissions for reliable
longitudinal analysis, exports, and clinical provenance.

## Deployment

| ID | Requirement |
| --- | --- |
| DEP-1 | PROlog is installed as a reusable Django app (`prolog_surveys`) inside PRomop. **PRomop's database is the only database**: PROlog's tables are created by PRomop's migrations, in PRomop's schema, alongside the OMOP CDM tables. PROlog defines no datastore of its own and no second copy of any record. |
| DEP-2 | Every response is linked to a participant record in the host: `PROLOG_PARTICIPANT_MODEL` names the model (PRomop `omop_core.Person`) and the link is **not nullable in normal operation**. Where the participant is not known, PROlog obtains one from the host's participant service rather than storing an unattached response (RUN-2). |
| DEP-3 | Survey definitions and themes are loaded from directories named in settings (`PROLOG_DEFINITION_DIRS`, `PROLOG_THEME_DIRS`) and/or from the database. A customer repository provides its content by mounting those directories at deployment; no rebuild of PROlog is required. |
| DEP-4 | The runner frontend is built once, brand-free; theme and survey content arrive at runtime from the API. |
| DEP-5 | A deployment is PRomop with `prolog_surveys` installed and a definition/theme directory mounted: one image, one database, one migration chain. A survey-only deployment is PRomop configured to expose nothing but the runner — still PRomop, still its database. |
| DEP-6 | There is no SQLite fallback. |
| DEP-7 | PROlog never writes to OMOP CDM clinical tables directly. It reads and creates `Person` rows through the host's participant service, and any clinical representation of an answer is produced by governed mapping (Mapping section), never as a side effect of capture. |

## Users and access

| Role | Capability |
| --- | --- |
| Platform administrator | Roles, organisations, retention settings, theme and definition registration. |
| Survey author | Draft questions, translations, routing, and preview (file-based until the designer ships). |
| Clinical/data curator | Search concepts and define/test/retire mappings (integrated profile). |
| Reviewer/approver | Approve a version, translation, or mapping for publication. |
| Participant | Start, save, resume, and submit available surveys. |
| Analyst | Export permitted de-identified data and mapping outcomes. |

In the integrated profile, use PRomop's existing identity and link responses
to the configured participant model; do not duplicate participant identity.
Each survey explicitly selects whether anonymous participation is permitted.
For an anonymous response no participant link exists unless the survey uses
identity capture and the participant opts in.

## Survey definition

| ID | Requirement |
| --- | --- |
| DEF-1 | A survey version is fully described by one JSON document conforming to `schema/survey-definition.schema.json`: identity (`slug`, `version`, `status`), languages and translation status, intro/completion copy, optional consent, participation and presentation settings, theme code, and ordered sections → questions → options with per-type config and visibility rules. |
| DEF-2 | Survey content is data, never code. Question and option text is never hard-coded in backend or frontend. |
| DEF-3 | Definitions are versioned: any wording or structural change that responses must be interpreted against is a new `version`. Published versions are immutable; every response records the exact version presented. |
| DEF-4 | At most one `active` version per `slug`. Activating a version archives the previous active one without altering historical responses. |
| DEF-5 | All participant-facing text is an i18n object keyed by language, falling back to `default_language`. Each non-default language carries `translation_status` (`machine` or `reviewed`); a version may not be activated while any offered language is `machine`. |
| DEF-6 | The backend validates a definition against the schema **and** against semantic rules on load: unique keys; the DAG rule (DEF-10); option references in conditions exist on the referenced question; `max_selections` ≤ option count; `optional_items` are real options; at most one email capture question; `link_identity` only in integrated profile. |
| DEF-7 | A `load_definition` management command registers or updates a definition file idempotently (draft) and can activate it; `validate_definition` runs DEF-6 without writing. |
| DEF-8 | The definition stored on `SurveyVersion.definition` is byte-equivalent to the validated file (normalised JSON), so the runner, exports and mappings all read the same snapshot. |
| DEF-9 | The schema is versioned (`schema_version`); the runner supports the current version and documents migrations for earlier ones. |
| DEF-10 | **A survey is a directed acyclic graph (DAG).** Questions are nodes; every `visible_if` condition (on a question or a section) and every `rows_from` reference is a directed edge from the dependent element to the question it depends on. An edge may only point to a question that appears **earlier** in presentation order (sections in array order, then questions in array order). Self-references, forward references, and therefore cycles are rejected at validation. |

### Survey graph

The DAG rule (DEF-10) is what makes the runner simple and the data
interpretable:

- **Presentation order is a topological order.** Visibility for the whole
  instrument is computed in one forward pass over the question list; no
  fixed-point iteration, no ambiguity about which answer "wins".
- **Cascade invalidation is well-defined.** When an answer changes, only the
  descendants of that node in the DAG can change visibility; the server walks
  forward from the changed question and clears exactly those answers (RUN-16).
- **Reachability is decidable at design time.** The validator can report
  questions that can never be shown (conditions on options that cannot be
  selected together) and the designer (final phase) can render the instrument
  as a graph.
- **Sections are nodes too.** A section's `visible_if` may reference only
  questions in earlier sections; every question in a hidden section is hidden.

JSON Schema cannot express ordering constraints, so the schema documents the
rule in its descriptions and the semantic validator (`validate_definition`,
DEF-6/DEF-7) enforces it. The rule is deliberately stricter than "acyclic":
requiring backward-only edges keeps definitions readable and guarantees
acyclicity without a cycle search. Backward jumps in *navigation* (a
participant returning to an earlier question) are not edges in this graph;
they are a runner feature (RUN-9) that re-evaluates the DAG forward from the
changed answer.

## Runner

### Eligibility, lifecycle, resume

| ID | Requirement |
| --- | --- |
| RUN-1 | The runner shows only `active` versions within their effective dates that the participant may access. Anonymous surveys (`participation.anonymous = true`) need no account; the response id is the sole credential and is treated as a secret. Anonymous here means the participant is not identified — the response is still bound to a person record (RUN-2), one carrying nothing that could name them. |
| RUN-2 | Starting a survey creates a response bound to the active version, the chosen language, and a participant record. For a signed-in participant that is their own `Person`; otherwise PROlog asks the host's participant service for a new `Person` with no identifying attributes and binds the response to it. A response is never created without one (DEP-2). |
| RUN-3 | Resume: for `browser_token`, the response id is kept in browser storage and the intro page offers **Continue** / **Start again** (start again is confirmed and abandons the previous response); for `account`, the participant's in-progress response is resumed on sign-in. |
| RUN-4 | Submission records server timestamps, marks the response immutable, and returns it read-only thereafter. Correction is a revision/new response, never an overwrite. |
| RUN-5 | Repeat administration (`participation.repeat`) is available to invited, non-anonymous participants only: at each due date a new invitation is sent and a distinct response is created for the scheduled or then-active version. Off by default. |

### Presentation and navigation

| ID | Requirement |
| --- | --- |
| RUN-6 | `presentation.mode = question` (default) renders one question per screen; `section` renders one section per screen. Both share the same navigation model and validation. |
| RUN-7 | Navigation walks the ordered list of **visible** questions computed by a pure function `(definition, answers) → visibleQuestions[]`, re-evaluated on every answer change. Newly revealed branch questions are inserted in order; hidden ones are removed. |
| RUN-8 | The URL identifies the current question (`/s/{slug}/q/{key}`) so browser back/forward work. |
| RUN-9 | An overview panel (`presentation.overview`) lists sections and visible questions with status (answered / skipped / current / unanswered / unreachable) and an answer summary; answered and reachable questions are navigable, future unreachable ones are inert. |
| RUN-10 | Progress shows the section position ("Section 2 of 7") and a bar over visible questions, recomputed as branches open/close. |
| RUN-11 | Optional data-free section interstitials (`presentation.section_interstitials`). |
| RUN-12 | An intro page shows title, intro copy, estimated time, anonymity statement (when anonymous), language selector, consent (if defined), and Start/Continue. The contact or identity capture step, when configured, is the `email` question asked in the wizard at its position in the definition (Save stores the address and the participant continues with Next / Finish; No thanks records the decline and moves on, which on the last question submits). A completion page shows completion copy and the read-only notice only — no data entry. |
| RUN-13 | The "Next" control reads "Finish" on the last visible question; single-choice selection does **not** auto-advance. |

### Answers, validation, branching

| ID | Requirement |
| --- | --- |
| RUN-14 | Every answer is autosaved the moment the participant moves on or changes it (per-answer upsert), with optimistic UI, retry with backoff, a visible saved indicator, and forward navigation blocked only if saving ultimately fails. |
| RUN-15 | The server validates each answer against the frozen definition: value shape per type, option keys, `max_selections`/`min_selections`, exclusive options, scale bounds, ranking completeness (except `optional_items`), matrix rows equal to the current source selection, text/number/date bounds, and visibility (an answer to a hidden question is rejected). The client mirrors these rules for UX but never replaces them. |
| RUN-16 | Changing a gating answer invalidates hidden/downstream answers server-side (cascade): the affected answer rows are deleted (or, for a matrix, pruned to surviving rows) and the response returns `invalidated: [keys]` so the client can sync its cache. |
| RUN-17 | Skip policy (`presentation.skip_policy`, default `soft`): advancing past an unanswered `required` question triggers a one-time confirmation; confirming stores an explicit skip `{"skipped": true}` distinct from "not reached". `required = false` questions skip silently. `hard` blocks advancing. Skipped questions remain revisitable. |
| RUN-18 | Completion requires every visible question to have an answer row (value or explicit skip); otherwise the API returns the missing keys and the runner navigates to the first. |
| RUN-19 | The language actually used is stored on the response; participants may switch language before starting, and mid-survey switching preserves answers. |

### Question types and answer shapes

| ID | Type | Control | Stored `value` |
| --- | --- | --- | --- |
| Q-1 | `info` | read-only text block | none |
| Q-2 | `single` | radio cards; `free_text` option reveals inline input | `{"option": k, "other_text"?: s}` |
| Q-3 | `dropdown` | searchable combobox; `options_source: iso3166_countries` provides a localized ISO 3166 list, inline options appended (e.g. "Prefer not to say") | `{"option": k}` |
| Q-4 | `multi` | checkbox cards; counter for `max_selections`; at the limit remaining cards are inert; `exclusive` options clear others | `{"options": [k…], "other_text"?: s}` |
| Q-5 | `scale` | segmented buttons `min..max` with endpoint or point labels | `{"value": n}` |
| Q-6 | `ranking` | sortable list with drag **and** keyboard/button reorder; `optional_items` may be left unranked | `{"order": [k…], "other_text"?: s}` |
| Q-7 | `matrix` | one row per fixed row or per option currently selected in `rows_from`; a segmented scale per row; legend once; rows stack vertically | `{"ratings": {row: n}}` |
| Q-8 | `text` | input or textarea (`multiline`, `max_length`) | `{"text": s}` |
| Q-9 | `number` | numeric input (`min_value`, `max_value`, `integer`) | `{"number": n}` |
| Q-10 | `date` | date input (`min_date`, `max_date`) | `{"date": "YYYY-MM-DD"}` |
| Q-11 | `email` | email input with the question's help copy in an info panel; equal-weight Skip | never stored as an answer — see CON-3/CON-4; the answer row records only `{"provided": true|false}` |
| Q-12 | any | explicit skip | `{"skipped": true}` |

### Consent, contact capture, identity capture

| ID | Requirement |
| --- | --- |
| CON-1 | When a definition declares `consent`, participants must actively agree before the first question. The attestation is stored with the consent version and timestamp as a separate record, never as an answer. |
| CON-2 | If a consent notice, intended use, or data-sharing term changes materially, participants are shown the updated notice and must agree before a future administration. Re-consent never changes or reopens consent for an already submitted response. |
| CON-3 | **Contact capture** (`email` question with `store_separately: true`): the address is validated and stored in a contact table with the survey version and consent text shown, **without any reference to the response or its answers**. It is never returned by the API, never joined in exports, and never logged. This is the exception, not the default (CON-4): it produces a mailing list and nothing else — no account, no way for the participant to reach their own data, and no way to honour a later access or erasure request about their answers. A deployment choosing it should be able to say why. |
| CON-4 | **Identity capture** (`email` question with `link_identity: true`) is the default way to ask for an address. The address is validated and sent only to the host's approved identity service, which gives an account to the `Person` the response is **already** bound to — promoting that person from unidentified to identified in place, with no data moved and no second record created. The account is created immediately and its address treated as unverified; nothing that existed before it is exposed to it until the participant confirms (decision 6). Where the address already belongs to a **different** participant, nothing is attached: the response stays where it is and the pair is recorded as a merge candidate (decision 7). The participant is told the same thing either way — saying an address is already registered would leak that it is. The email is not stored in answers, definition JSON, logs, exports, or telemetry; PROlog keeps only `identity_linked_at`, an answer row recording `{"provided": true}`, and, for a conflict, the two participant ids. The call is idempotent per response, so a retry cannot create duplicates; on failure the response stays unidentified and submission is unaffected. |
| CON-5 | A survey has at most one email capture question, placed at the start or end of the instrument by its position in the definition. Leaving it blank never blocks submission and never creates a record. |
| CON-6 | Unidentified responses store no PII and no IP addresses; the `Person` they are bound to carries no identifying attribute until an account is created. Throttling uses hashed, short-lived keys. |
| CON-7 | Account creation is a participant's choice and never a condition of answering. Leaving the email question blank, or skipping it, submits the response exactly as it stands and leaves the person unidentified. Nothing about the instrument, its questions, or its completion changes based on whether an account exists. |
| CON-8 | A deployment must describe, in the instrument's intro and consent copy, what actually happens to the participant's data — including that giving an email creates an account against which their answers are held, when the instrument does that. PROlog will not describe an instrument as anonymous on the deployment's behalf: the runner renders the anonymity statement the definition supplies, and it is the deployment's responsibility that the statement is true. |

## Theming

| ID | Requirement |
| --- | --- |
| THM-1 | A theme is a directory containing `theme.json` (conforming to `schema/theme.schema.json`) and its assets (logo, decorative SVGs, self-hosted font files). PROlog ships one neutral theme, `themes/default`. |
| THM-2 | Themes are registered from `PROLOG_THEME_DIRS` at first use (the registry scans lazily on the first definition, theme or health request; a restart rescans) and exposed by `GET /api/run/themes/{code}/`; assets are served under `/api/run/themes/{code}/assets/…` with long-lived caching. |
| THM-3 | A survey selects a theme with its `theme` code; an unknown or missing code falls back to `default` and is logged. |
| THM-4 | The runner applies a theme at load time by setting CSS custom properties (`--p-primary`, `--p-ground`, …), injecting `@font-face` rules for declared faces, and switching layout flags (`immersive_intro`, `copy_alignment`, `logo_placement`). Component styles reference tokens only; no component references a brand color directly. |
| THM-5 | A theme may declare `light` only (light-only product) or `light-dark`; the runner honours `prefers-color-scheme` only for `light-dark` themes. |
| THM-6 | Themes may override runner chrome strings (`strings`) per language but can never alter survey content. |
| THM-7 | Theme changes must not require a frontend rebuild; a theme is validated on registration and rejected with a clear error if invalid. |
| THM-8 | Accessibility is enforced independently of theme: minimum text size, focus ring visibility, and the requirement that `accent`/`secondary` are not used for small text are built into components, and a contrast check for `ink`/`primary` on `surface`/`ground` runs on theme registration (warning below 4.5:1). |

## Designer (final phase)

- Create surveys with title, stable code, description, audience/context,
  effective dates, languages, consent settings, theme, and an
  anonymous-participation setting.
- Compose ordered sections and information, single/multi-choice, short and
  long text, number, date, scale, ranking, and matrix questions; configure
  stable machine keys, validation, answer options, `Other` text, selection
  limits, help text, and requiredness.
- Configure prior-answer visibility rules, including selected-answer matrices;
  reject cycles and unreachable questions.
- Maintain separately reviewable translations keyed to canonical content.
- Support non-persisting preview, review/approval, publication, pausing, and
  retirement without changing historical records.
- Keep published versions immutable; a change creates a new draft.
- The designer reads and writes the same definition JSON the runner consumes;
  it is an editor over the schema, not a second model. Export/import of the
  definition file must round-trip.
- Configure optional repeat administration (interval, start, optional end,
  version policy) for invited participants.

## Optional mapping and OMOP write-back (integrated profile)

- Every response is retained in its original submitted form whether or not it
  has an OMOP mapping. Raw survey capture is the source record; mappings create
  additional derived representations and never replace, mutate, or discard the
  original answer.
- At design time, curators may map a question, option, calculated score, or
  multi-answer rule to one or more OMOP concepts/tables.
- When a designer adds or identifies a wellbeing/function question, prompt them
  to choose whether to consider an ECOG Performance Status mapping, a Karnofsky
  Performance Status mapping, both, or neither. For the selected score(s), the
  mapping assistant suggests a proposed mapping for every response option (or
  permitted response range) and shows its rationale. Suggestions are drafts:
  the authorised designer must review, edit where needed, and approve them;
  they are never applied automatically.
- A mapping declares source fields, expression/version, target table/concept,
  value representation, event-date strategy, and rationale.
- Mapping is optional at every level. It is not a publishing or submission
  prerequisite.
- Target standard OMOP `observation`, `note`, or `note_nlp` tables as
  appropriate. `measurement` or other OMOP domains require explicit governance
  before use. Every generated row must link to its response, input answers,
  mapping version, and execution actor/job.
- Evaluate approved mappings after submission (or explicitly on an approved
  draft), idempotently. Record success, no-result, error, and superseded
  states. A failure never loses raw answers.
- Example: a clinically approved calculation can transform wellbeing/function
  answers into an ECOG value. Its instrument, algorithm, concept/value
  convention, vocabulary release, and clinical approval must be retained.

## Data model

Tables are declared by the `prolog_surveys` Django app and live in **PRomop's
database**, created by PRomop's migrations alongside the OMOP CDM tables. There
is no PROlog database. The app adds tables; it never alters OMOP CDM tables, and
clinical representations of answers are produced only by governed mapping.

| Entity | Purpose |
| --- | --- |
| `Survey` | Stable identity (`slug`), lifecycle metadata, theme code, anonymous-participation policy, effective dates. |
| `SurveyVersion` | Immutable snapshot: `version`, `status`, `definition` JSON (DEF-8), `schema_version`, `published_at`. |
| `SurveyQuestion`, `SurveyOption` | Materialised on publish from the definition (keys, types, order) to give mappings and analytics stable foreign keys. Read-only projections; the JSON stays authoritative. |
| `SurveyResponse` | Attempt/submission: version FK, language, status, `started_at`, `submitted_at`, `last_question_key`, **participant FK (DEP-2) — always set**, `identity_linked_at` (null until an account exists). No IP, no PII. |
| `SurveyAnswer` | Typed raw answer per (response, question key): `value` JSON as in Q-1…Q-12, selected option keys, `updated_at`. |
| `SurveyConsent` | Consent attestation: response, consent version, text hash, timestamp. |
| `SurveyContact` | Contact capture (CON-3) only — the exception path: survey version, email, consent text shown, timestamp. **No response FK.** Identity capture (CON-4) writes nothing here; the address goes to the host's identity service and is never persisted by PROlog. |
| `ResponseRevision` | Correction audit for post-submission revisions. |
| `SurveyInvitation`, `SurveyAdministration` | Invited participants and repeat-administration schedule/occurrences (RUN-5). |
| `ConceptMapping`, `MappingExecution` | Optional governed mapping and idempotent execution provenance (integrated). |

`SurveyAnswer` is authoritative raw capture. Do not store all answers only as
opaque JSON on the response or use a generic EAV table as the sole
representation; one row per answered question with a typed JSON value and
indexed option keys is the minimum.

## API boundary

Runner (anonymous surveys: the response UUID is the capability token; account
surveys: session/JWT):

| Method & path | Purpose |
| --- | --- |
| `GET /api/run/surveys/{slug}/?lang=` | Active version's definition for the runner, localized, with theme code, ETag-cached. Internal `notes` stripped. |
| `GET /api/run/themes/{code}/` and `/assets/{path}` | Theme document and assets (THM-2). |
| `GET /api/run/options/{source}/?lang=` | Built-in option lists (ISO 3166). |
| `POST /api/run/responses/` `{slug, language, consent?}` | Create response, obtaining or creating the participant `Person` it binds to (RUN-2) → `{id, version, …}`. The person id is never returned to an unauthenticated runner. |
| `GET /api/run/responses/{id}/` | Status, language, all answers, visible-question list. |
| `PUT /api/run/responses/{id}/answers/{key}/` | Upsert one answer (autosave). Validates (RUN-15), cascades (RUN-16), returns `{answer, invalidated}`. |
| `POST /api/run/responses/{id}/submit/` | Complete (RUN-18). |
| `POST /api/run/responses/{id}/contact/` `{email}` | Contact capture (CON-3). |
| `POST /api/run/responses/{id}/identity/` `{email}` | Identity capture (CON-4): the host creates or finds the account for the response's existing person. Never returns the email or the person id. |

Designer and curation (later phases): `GET/POST /api/surveys/`,
`GET/PATCH /api/surveys/{id}/draft/`, `POST /api/survey-versions/{id}/preview/`,
`/publish/`, `GET/POST /api/concepts/search/`, `/api/mappings/`.

All non-runner endpoints require organisation-scoped object permissions and
audit logging. Runner endpoints are throttled per response id and per hashed
client key. All endpoints carry an API version.

## Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR-1 | Protect sensitive data: least privilege, encryption in transit and at rest, audit log, retention and deletion policy, no PHI or PII in client telemetry or server logs. |
| NFR-2 | Complete applicable privacy/consent review before any customer launch. |
| NFR-3 | WCAG 2.2 AA: real `fieldset`/`legend` groups, ≥44 px targets, visible focus, keyboard-operable ranking with live announcements, `lang` attribute per language, no information by colour alone, `prefers-reduced-motion` honoured. |
| NFR-4 | Reproducibility: instrument, theme, mapping, calculation, and vocabulary versions are immutable and recorded. |
| NFR-5 | Backups, monitoring, autosave conflict handling (last-write-wins per answer with `updated_at`), and permitted export (CSV: one row per response, one column per question, multi-selects exploded, matrix rows exploded; contacts exported separately). |
| NFR-6 | Text expansion: layouts tolerate ~30 % longer strings than the default language. |
| NFR-7 | Runner performance: definition and theme cached with ETags; first meaningful paint under 2 s on a mid-range mobile over 3G; answer save round-trip under 300 ms p95 on the reference deployment. |
| NFR-8 | Automated tests: schema/semantic validation, per-type answer validation, branching cascade, navigation model (pure functions), theme application, and end-to-end happy path plus both branch directions. |

## Delivery sequence

See [implementation-plan.md](implementation-plan.md). In summary:

1. Neutral scaffold, deployment profiles, definition schema and loader.
2. Response engine API (create, autosave, cascade, submit, contact).
3. Runner core (intro, wizard, navigation, simple question types, resume).
4. Complex question types (ranking, dynamic matrix, limits, exclusives).
5. Theming.
6. i18n, accessibility, export, hardening, first customer launch.
7. Accounts: identity capture and account creation, consent, repeat
   administration.
8. Designer and preview.
9. Mapping review, concept search, OMOP write-back.

## How the move happens

The steps that take the backend from a standalone service to an app inside PRomop —
the stack pins, the app boundary, the migrations, RUN-2, and retiring the standalone
profile — are planned in [`promop-migration-plan.md`](promop-migration-plan.md).

## Open decisions

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | ~~Should the first customer launch use the standalone profile?~~ | **Superseded 2026-08-31.** There is no standalone profile. Every deployment is PRomop with `prolog_surveys` installed, and every response is bound to a `Person` in PRomop's database. The trade this accepts: PROlog is no longer independently deployable, and a customer who wants surveys without an OMOP store now takes PRomop anyway. Revisit only if such a customer appears. |
| 2 | Package boundary: publish `prolog_surveys` as an installable Python package plus a versioned runner bundle, or consume by git tag? | Git tag + container image for the first launch; package later. |
| 3 | Who may register themes and definitions in production: file mount only, or also an admin upload? | File mount only until the designer ships. |
| 4 | ~~Should there be a *linked* contact option in addition to unlinked contact capture?~~ | **Superseded 2026-08-31.** Linked is the default and it is stronger than the third mode once contemplated: an address creates a real account (CON-4), not a row with a foreign key. What the old recommendation warned about still holds and is now a requirement rather than a caveat — an instrument that does this is not anonymous for those participants, and its intro and consent copy must say so (CON-8). |
| 5 | Where does the `Person` for an unidentified response come from — created eagerly when the response is created, or lazily at first answer? | Eagerly, at response creation: it keeps the participant FK non-null everywhere (DEP-2) and avoids a second code path. The cost is a `Person` row per abandoned attempt, which the abandoned-response retention job must now clean up as well (NFR-1). |
| 6 | Should an account created from an email question be usable immediately, or only after the participant confirms the address? | **Decided 2026-09-02: create it, treat the address as unverified, and expose nothing that existed before it to that account until the participant follows a confirmation link.** The account has to exist for the person to be promoted in place (CON-4) without moving any answer; keeping it inert until confirmed is what makes a mistyped address harmless. A typo still mints an account nobody asked for — it can see nothing, and the retention job takes it with the response. |
| 7 | When the address a participant supplies already belongs to a **different** `Person`, what happens? | **Decided 2026-09-02: attach nothing.** The response stays bound to the person it was minted with, and a merge candidate is recorded for a separate reconciliation path. Merging two patient records is a clinical-safety operation, not a survey side effect, and a confirmed address is not proof that two records are the same human. The cost is accepted: a respondent who really is that patient does not get their survey joined to their record automatically. Never the host service's current behaviour, which returns the other person and re-points its `PatientUser` — `PatientUser` is one-to-one on both sides, so the account cannot sit on the person the answers are bound to. |
| 8 | ~~RUN-2 has no implementation on either side.~~ | **Done 2026-09-02.** `PROLOG_PARTICIPANT_FACTORY` is implemented and called when no participant resolves; PRomop provides `create_unidentified_person`. `MintedParticipant` records which of the host's rows the app created. The response FK stays **nullable** for now: the runner binds every response it creates, so the invariant holds in practice, and flipping the column needs a backfill and makes a factory mandatory — both better done once, with CON-4. |
| 9 | Does PROlog replace the host's own survey feature, where it has one? | **Decided 2026-09-02: yes.** In PRomop that is `omop_core.Survey` / `PatientSurveyResponse`, shipped as PHR-S FM phase 4a. One survey model, one renderer, one answer to where a participant's responses are. Two consequences to plan for rather than discover: existing responses need a migration path, and PRomop's PH.2.1 conformance claim currently rests on the feature being retired, so it has to be re-examined against this one. |
