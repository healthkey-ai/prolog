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
instrument. It proposes a Follicular Lymphoma survey in English, Spanish, and
Portuguese with six sections. When a survey is configured to allow anonymous
participation, a participant may complete and submit it without an existing
PRomop identity:

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
clinically. For an anonymous survey, the instrument may present an optional
email capture at either the beginning or the end, according to its approved
survey design. Supplying an email is an identity-creation/linking action, not
an ordinary survey answer: PRomop creates a new patient record and attaches the
response and its approved OMOP-derived rows to that patient identity. Leaving
it blank must neither block submission nor create a patient record. The email
and the consent for this action require explicit privacy controls.

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
not duplicate patient identity. Each survey explicitly selects whether
anonymous participation is permitted. For an anonymous response, no `Person`
link exists unless the participant opts to supply an email in the configured
identity-capture step. PRomop then creates the patient record and links that
same response to it. This is optional and must not turn other anonymous
responses into pseudonymous records.

## Functional requirements

### Designer

- Create surveys with title, stable code, description, audience/context,
  effective dates, language, consent settings, and an anonymous-participation
  setting.
- For surveys that permit anonymous participation, configure an optional
  identity-capture step at the start or end of the instrument. It must clearly
  explain that an email creates a PRomop patient record and links the submitted
  survey and any approved OMOP mappings to it.
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
- An anonymous participant may submit without an email. If they elect to
  provide one, validate and send it only to PRomop's approved patient-identity
  creation service; on success, attach the response to the newly created
  `Person` before mapping execution. Email is not stored in `SurveyAnswer`,
  response schema JSON, logs, analytics exports, or browser telemetry.
- Store the language actually used; initial support is English, Spanish, and
  Portuguese.

### Optional mapping and OMOP write-back

- Every response is retained in its original submitted form, whether or not it
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
| `Survey` | Stable identity, lifecycle metadata, and anonymous-participation policy. |
| `SurveyVersion` | Immutable instrument snapshot. |
| `SurveyPage`, `SurveyQuestion`, `SurveyOption` | Ordered versioned structure and choices. |
| `SurveyRule`, `SurveyTranslation` | Routing and reviewed localised content. |
| `ConceptMapping` | Optional governed mapping expression, targets, concepts, status, and rationale. |
| `SurveyResponse` | Participant attempt/submission; nullable FK to Person, populated if authenticated or if optional email created a patient record. |
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

The identity-capture payload is handled separately from survey answers. It is
submitted over the same protected session but routed directly to PRomop's
patient-record creation service; PROlog retains only the resulting `Person`
link and a non-sensitive consent/audit outcome. It must be idempotent so a
retry cannot create duplicate patient records. If record creation fails, the
participant can still submit anonymously unless they choose to retry; raw
answers are never discarded.

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
- `POST /api/responses/{id}/identity/` — for a survey that permits anonymous
  participation, optionally submit the consented email to PRomop to create a
  patient record and link this response. The email is never returned by this
  API.
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

1. Confirm PRomop installation, auth, tenancy, patient-record creation service,
   anonymous mode, and deployment.
2. Add PRomop migrations plus definition/version/response/audit APIs.
3. Build runner, then designer and preview.
4. Enter/review FLF content, translations, and routing tests.
5. Add mapping review, concept search, and write-back.
6. Validate accessibility, privacy, security, export, and clinical correctness.

## Decisions needed

- Does a participant need to be shown and actively agree to an updated consent
  notice before a future survey administration, when the notice, intended use,
  or data-sharing terms change? This is what “re-consent” means here; it does
  not mean asking again for consent for an already submitted response.
