# PROlog requirements

**Status:** living draft  
**Updated:** 2026-08-28  
**Name:** PROlog (repository rename pending)

## Purpose

PROlog designs, publishes, runs, and analyses patient surveys. It has two
experiences: a **designer** for authorised staff to compose versioned instruments
and governed OMOP mappings, and a **runner** for participants to complete,
save, resume, and submit them.

This is not a separate clinical-data silo. Survey definitions, raw responses,
optional mapping provenance, and any derived clinical facts are stored in the PRomop
database/application (`~/promop`). PROlog is a Django/React application
deployed with, or installed as an app in, PRomop.

## Reference inputs

### FLF Global Patient Survey 2026, confidential draft v0.6

The supplied document is the first content reference, not a final approved
instrument. It proposes an anonymous Follicular Lymphoma survey in English,
Spanish, and Portuguese with six sections:

1. Participant and FL journey.
2. Treatment history and access.
3. CAR-T and bispecific antibodies.
4. Decision-making burden and support.
5. Quality of life, treatment goals, and burden.
6. Support gaps and FLF resources.

It includes around 29 numbered questions/subquestions. Required controls are
country dropdowns, single choice, multi-select with limits, 1–5 Likert scales,
ranking, free text, conditional branching, and a conditional matrix for selected
symptoms. Examples include access-delay causes after `Yes`, and watch-and-wait
symptom questions after `Yes`. The first implementation must preserve supplied
wording/options as content pending FLF approval; it must not reinterpret them
clinically. The proposed optional email/future-contact question requires an
explicit consent and privacy decision.

### HealthTree survey capability

HealthTree establishes useful baseline behaviour: draft/active/archive lifecycle,
multi-page wizard, non-persisting preview, autosave, started/completed timestamps,
completion percentage, and consent handling. It stores answers in a mutable
per-user Firestore document. PROlog retains the UX but uses normalized,
versioned, immutable submissions for reliable longitudinal analysis, exports,
and clinical provenance.

## Users and access

| Role | Capability |
| --- | --- |
| Platform administrator | Roles, organisations, retention settings. |
| Survey author | Draft questions, translations, routing, and preview. |
| Clinical/data curator | Search concepts and define/test/retire mappings. |
| Reviewer/approver | Approve a version or mapping for publication. |
| Participant | Start, save, resume, and submit available surveys. |
| Analyst | Export permitted de-identified data and mapping outcomes. |

Use PRomop's existing identity and link responses to `omop_core.Person`; do
not duplicate patient identity. Anonymous campaigns require an explicit policy:
no person link, or a consented pseudonymous participant record.

## Functional requirements

### Designer

- Create surveys with title, stable code, description, audience/context,
  effective dates, language, and consent settings.
- Keep published versions immutable. A change makes a new draft; every response
  retains the exact presented version.
- Compose ordered pages/sections and information, single/multi-choice, short and
  long text, number, date, Likert, ranking, and matrix questions.
- Configure stable machine keys, validation, answer options, `Other` text,
  selection limits, help text, and requiredness.
- Configure prior-answer visibility/skip rules, including selected-answer
  matrices; reject cycles and unreachable pages.
- Maintain separately reviewable translations keyed to canonical content.
- Support non-persisting preview, review/approval, publication, pausing, and
  retirement without changing historical records.

### Runner

- Show only published, in-date surveys the participant may access.
- Offer page navigation, progress, accessible controls, server-side validation,
  and conditional routing.
- Autosave drafts and resume authenticated attempts.
- Final submission records server timestamps and becomes immutable; correction
  is a revision/new response, never an overwrite.
- Capture required consent as a versioned attestation, not an ordinary answer.
- Store the language actually used; initial support is English, Spanish, and
  Portuguese.

### Optional mapping and OMOP write-back

- Every response is retained in its original submitted form, whether or not it
  has an OMOP mapping. Raw survey capture is the source record; mappings create
  additional derived representations and never replace, mutate, or discard the
  original answer.
- At design time, curators may map a question, option, calculated score, or
  multi-answer rule to one or more OMOP concepts/tables.
- A mapping declares source fields, expression/version, target table/concept,
  value representation, event-date strategy, and rationale.
- Mapping is optional at every level: a survey, question, option, or response
  may have no mapping. It is not a publishing or submission prerequisite.
- Target standard OMOP `observation`, `note`, or `note_nlp` tables as
  appropriate. `measurement` or other OMOP domains require explicit
  governance before use. Every generated row must link to its
  response, input answers, mapping version, and execution actor/job.
- Evaluate approved mappings after submission (or explicitly on an approved
  draft), idempotently. Record success, no-result, error, and superseded states.
  A failure never loses raw answers.
- Example: a clinically approved calculation can transform wellbeing/function
  answers into an ECOG value. Its instrument, algorithm, concept/value
  convention, vocabulary release, and clinical approval must be retained.

## Data model and PRomop ownership

Create these new tables through PRomop Django migrations in a
`prolog_surveys` app (or equivalent installed reusable app). They do not alter
OMOP CDM tables for raw answers or configuration.

| Entity | Purpose |
| --- | --- |
| `Survey` | Stable identity and lifecycle metadata. |
| `SurveyVersion` | Immutable instrument snapshot. |
| `SurveyPage`, `SurveyQuestion`, `SurveyOption` | Ordered versioned structure and choices. |
| `SurveyRule`, `SurveyTranslation` | Routing and reviewed localised content. |
| `ConceptMapping` | Optional governed mapping expression, targets, concepts, status, and rationale. |
| `SurveyResponse` | Participant attempt/submission; FK to Person where applicable. |
| `SurveyAnswer` | Typed raw answer, source option, and canonical composite JSON. |
| `ResponseRevision`, `SurveyConsent` | Correction audit and consent attestation. |
| `MappingExecution` | Idempotent run/outcome and produced OMOP-row provenance. |

`SurveyAnswer` is authoritative raw capture: it retains the original submitted
answer text/value, selected options, and a typed canonical value plus JSON for
rankings/matrices. The version snapshot gives it immutable meaning. Mappings are
separate, optional derived records. Do not store all answers only as opaque JSON
or use a generic EAV table as the sole representation.

PRomop already provides `Person`, `Concept`, `Observation`, `Note`, and
`NoteNlp`. PROlog uses foreign keys to those models as appropriate and uses
PRomop's established clinical write path/provenance fields. Migration
dependencies and app registration belong in `~/promop`, not in a parallel
SQLite database.

## Architecture

```text
React designer / participant runner
               │ HTTPS JSON API
               ▼
Django PROlog survey app (inside/alongside PRomop)
               │
  ┌────────────┴─────────────┐
  ▼                          ▼
PROlog survey tables     PRomop OMOP CDM tables
definitions, original    Person, Concept, Observation,
answers, rules, audit    Note, NoteNlp, …
```

The browser never writes directly to the database or evaluates clinical mappings.
The backend validates the frozen version, executes approved mappings, and audits
every write.

## Initial API boundary

- `GET/POST /api/surveys/` — designer list/create.
- `GET/PATCH /api/surveys/{id}/draft/` — edit unpublished version.
- `POST /api/survey-versions/{id}/preview/`, `/publish/`.
- `GET /api/run/surveys/{code}/` — eligible runner schema.
- `POST/PATCH /api/responses/` — create/autosave; `POST .../submit/` finalises.
- `GET/POST /api/concepts/search/`, `/api/mappings/` — curator workflow.

All endpoints require organisation-scoped object permissions, audit logging, and
an API versioning strategy.

## Non-functional requirements

- Protect sensitive data: least privilege, encryption, audit log, retention and
  deletion policy, and no PHI in client telemetry.
- Complete applicable privacy/consent review before launch.
- Target WCAG 2.2 AA, including keyboard flow, labels/errors, focus management,
  responsive design, and screen-reader-safe matrices.
- Preserve reproducibility: instrument/mapping/calculation/vocabulary versions
  and provenance are immutable.
- Provide backups, monitoring, autosave conflict handling, and permitted export.

## Delivery sequence

1. Confirm PRomop installation, auth, tenancy, anonymous mode, and deployment.
2. Add PRomop migrations plus definition/version/response/audit APIs.
3. Build runner, then designer and preview.
4. Enter/review FLF content, translations, and routing tests.
5. Add mapping review, concept search, and write-back.
6. Validate accessibility, privacy, security, export, and clinical correctness.

## Decisions needed

- Is FLF actually anonymous, or is longitudinal `Person` linkage permitted?
  How is optional email segregated?
- Which PRomop organisation owns each survey/response?
- What invitation/identity provider is used?
- Who approves publication, translations, mappings, scoring, and clinical writes?
- What validated wellbeing-to-ECOG scoring definition and concept/value convention
  will be used?
- Are repeat administrations separate responses, scheduled series, or both?
- What retention, withdrawal, deletion, export, and re-consent rules apply?
