# Moving the PROlog backend into PRomop

> **Artifacts this describes:** [`requirements.md`](requirements.md) — the 2026-08-31 revision this
> plan executes · [`implementation-plan.md`](implementation-plan.md) — the phases it amends ·
> [`deployment.md`](deployment.md), [`integration.md`](integration.md) — the runbooks it retires and
> replaces · `backend/prolog_surveys/` — the app that moves.

**Decisions taken 2026-09-02**, which this plan implements:

1. **Wait for the PRomop-hosted runner.** No further launch is prepared on the standalone profile.
2. **The survey app takes PRomop's Django**, 5.2.6, rather than PRomop taking PROlog's 6.1.
3. **`prolog_surveys` becomes an app inside PRomop**, and its tables are created in PRomop's schema
   by PRomop's migration chain.
4. **Clinical meaning of answers is deferred** (DEP-7 stands; nothing maps answers into OMOP yet).

Phases are lettered M0–M4 so they cannot be confused with the numbered phases in
[`implementation-plan.md`](implementation-plan.md), which they cut across.

---

## What moves, and what does not

| Moves into PRomop | Stays in this repository | Retired |
| --- | --- | --- |
| `prolog_surveys/` — models, engine, API, management commands, templates | the definition and theme **schemas** and their manuals | `prolog/` project settings, `settings_dev` |
| its five migrations, applied by PRomop | the runner front end **source** | the standalone Docker image and compose stack |
| the built runner assets, served by PRomop | `examples/`, `themes/`, the shared test vectors | `PROLOG_PROFILE` and everything selected by it |

PROlog stays public and keeps its own repository, tests and CI. What ends is the *deployment*: there
is no PROlog service, no PROlog database, and no PROlog image.

---

## M0 — Take PRomop's pins

**Smaller than it looks.** The dependency gap was the reason to doubt this direction; measured, it is
one API.

The only Django 6-only interface PROlog uses is the multi-backend mail API introduced in 6.0 — the
`MAILERS` setting and `django.core.mail.mailers`:

| Site | Today | On 5.2.6 |
| --- | --- | --- |
| `prolog/settings.py:205` | `MAILERS = {"default": {"BACKEND": …}}` | `EMAIL_BACKEND = …` |
| `prolog_surveys/invitations.py:14` | `from django.core.mail import … mailers` | `… get_connection` |
| `prolog_surveys/invitations.py:256` | `mailer = mailers.default` | `mailer = get_connection()` |
| `prolog_surveys/tests/test_invitations.py:316` | patches `invitations.mailers` | patches the connection factory |

The context-manager and `send_messages()` contract are identical on both, so `send_pending()` — which
opens one session for the batch and checks the returned count — is unchanged apart from how it
obtains the connection.

Everything else PROlog touches predates 5.2 by years. The DRF surface in use is
`serializers`, `status`, `exceptions`, `Response`, `APIClient`, `SimpleRateThrottle`, `APIView` —
all present and unchanged in 3.15.2. `STORAGES` is 4.2+. Nothing uses `db_default`,
`GeneratedField`, `LoginRequiredMiddleware`, `CompositePrimaryKey`, or the template-partials work.

**Ranges, not pins.** The app must *accept* what PRomop pins rather than pin against it: an exact
pin fails resolution the moment the host takes a patch release, which happened within a day —
PRomop moved 5.2.6 → 5.2.17 and DRF 3.15.2 → 3.17.2 while this was being written, and
`Django==5.2.6` in the app made its image unbuildable. So: `Django>=5.2.6,<6.0`,
`djangorestframework>=3.15.2,<4`, `django-cors-headers>=4.4,<5`, `whitenoise>=6.7,<7` — wide enough
for the host to move, narrow enough to exclude the majors the app has not been run on. `psycopg`
already agrees (3.3.x both sides). Both ends of the range are tested, so "compatible" is a claim
with a run behind it rather than a range someone guessed.

**And PRomop's Python.** Its image is `python:3.12-slim`, so `requires-python` is `>=3.12`, not
`>=3.13` — pip refuses the wheel outright otherwise (`Package 'prolog' requires a different Python:
3.12.14 not in '>=3.13'`). The suite passes on 3.12 unchanged; the ruff target moves with it.

**The image needs `git`.** PRomop installs the app from the public repository by commit, and
`python:3.12-slim` ships without git, so the build stage has to add it.

**Policy change to record in `CLAUDE.md`.** "Always the latest stable releases" no longer applies to
the backend: PROlog's backend follows PRomop's pins, because it runs in PRomop's process. The
front end keeps its own stack — it is built, not imported, and shares no runtime with PRomop.

> **Verified 2026-09-02.** The pins were taken, the mail API ported, and the full backend suite run
> against Django 5.2.6 / DRF 3.15.2 / cors 4.4.0 / whitenoise 6.7.0 — PRomop's exact versions — in
> both the standalone and the `auth.User` harness profiles. Both green, no other change needed.
> `make lint` (ruff, format, `makemigrations --check`, the append-only guard) is clean, so the
> downgrade produced no migration drift.

---

## M1 — The app becomes a PRomop app

**Getting the code there.** Three options, in order of preference:

1. **A versioned dependency.** PROlog publishes `prolog-surveys` from this public repository; PRomop
   pins a version in `requirements.txt`. Keeps one source of truth, makes upgrades a pin bump, and
   matches how PRomop consumes everything else.
2. **git subtree** into `promop/prolog_surveys/`, if packaging proves a distraction. Vendored code
   with a recorded upstream; upgrades are a subtree pull.
3. **A copy.** Fastest, and the only option that guarantees drift. Choose it only with a date on
   which it stops being a copy.

**Wiring.** `prolog_surveys` in `INSTALLED_APPS`; the runner URLs mounted under a prefix PRomop
chooses; PROlog's DRF settings merged into PRomop's rather than replacing them — in particular the
`run.*` throttle scopes, which PRomop's own viewsets do not declare and which must not disturb its
`anon 60/minute` / `user 300/minute` defaults.

**Authentication is the part that needs a decision, not a wiring change.** PROlog's runner endpoints
are deliberately unauthenticated: the response id is a capability token and the sole credential
(RUN-1). PRomop's DRF default is `IsAuthenticated`, and its permission layer resolves a `person_id`
per object (`_OmopFilterMixin`, `PatientSelfScopePermission`). These do not compose by accident.
The runner views must opt out of PRomop's default explicitly, keep their own throttles, and be
listed somewhere a reviewer can see the whole set of endpoints that answer without a session.

**Serving the runner.** PRomop already resolves a front-end root and serves it through WhiteNoise.
The built runner is another directory under that root, reached at its own prefix. The definition and
theme directories are mounted as they are today (`PROLOG_DEFINITION_DIRS`, `PROLOG_THEME_DIRS`) —
that part of DEP-3 does not change.

---

## M2 — Tables into PRomop's schema

`prolog_surveys` has five migrations. Installed into PRomop as a new app, Django applies them
natively: no renumbering, no squash, no merge migration, and no interleaving with `omop_core`'s 155.
The app's tables are additive and touch no OMOP CDM table (DEP-7).

Three things change in them:

- **`SurveyResponse.participant` targets `omop_core.Person` unconditionally.** `0005_participant`
  stops being conditional on a setting.
- **The FK becomes non-null** — but only after M3, because until then there is nothing to bind an
  unidentified respondent to.
- **`SurveyInvitation.participant`** likewise.

**Reshape now, not later.** PROlog has no release tag, so its migrations may still be rewritten once.
That window closes when they land in PRomop, after which they are PRomop's and append-only under
PRomop's rules. If the five are to be collapsed into one clean initial migration, this is the moment.

**Data.** None to migrate. The only PROlog database that exists is the FLF staging deployment, whose
contents are a smoke-test response and nothing else; it is discarded with the deployment in M4.

---

## M3 — RUN-2: binding a response to a person

This is the requirement with no implementation on either side, and the one M2's non-null FK waits on.

### The gap

RUN-2 says a response is always bound to a `Person`, and that where the participant is not signed in
PROlog "asks the host's participant service for a new `Person` with no identifying attributes".
PRomop's participant service cannot do that. `resolve_or_create_person(identity, …)`
(`patient_portal/services.py:125`) resolves or provisions a person **for an identity**, and every
path through it ends at `PatientUser.objects.create(identity=identity, person=person)` (`:181`). An
anonymous respondent has no `Identity`, so there is nothing to pass it.

The implementation plan names a `PROLOG_PARTICIPANT_FACTORY` hook for exactly this. Nothing
implements it in either repository.

### Proposal

**A second host primitive, beside the existing one.**

```python
# promop — patient_portal/services.py
def create_unidentified_person(*, source: str) -> Person:
    """Create a Person with no Identity, no PatientUser, and no identifying attribute.

    The counterpart to resolve_or_create_person, which provisions *for an identity*.
    This mints a person who is not anyone yet: the subject of a survey response
    that may never be claimed. `source` records what minted it (e.g. "prolog").
    """
```

PROlog reaches it through `PROLOG_PARTICIPANT_FACTORY = "patient_portal.services.create_unidentified_person"`,
the same import-string pattern as `PROLOG_PARTICIPANT_RESOLVER`, and never imports PRomop directly.

Four properties make it safe to call from a public endpoint:

**1. It creates the `PatientRecord`.** PRomop issue #883 is the same primitive built without one:
persons created through `find_or_create` have no `PatientRecord`, so record derivation answers 404 —
*"invisible in the portal, and there is no API call we can make to fix it. 39 patients ended this way
in our 2026-08-31 migration."* Minting a person per survey start would reproduce that at a different
order of magnitude. The row is created; derivation is **not** run, because there is nothing clinical
to derive.

**2. It is marked, without touching an OMOP table.** DEP-7 forbids the survey app from altering OMOP
CDM tables, and PRomop's `Person` has no free source-value column to borrow. So the marker lives in
the survey app, as a table it owns:

```python
# prolog_surveys — one row per person this app minted
class MintedParticipant(models.Model):
    participant     = OneToOneField(PARTICIPANT_MODEL, on_delete=CASCADE)
    created_at      = DateTimeField(auto_now_add=True)
    identified_at   = DateTimeField(null=True)   # set when the person gains an account
```

A person that appears here with `identified_at IS NULL` is a survey respondent nobody has claimed.
Every denominator, export and cohort query that counts patients excludes them, through one helper
rather than a repeated `.exclude()`. A pre-existing patient who takes a survey never appears in this
table at all — the distinction the marker exists to make.

**3. Promotion happens in place.** When a respondent supplies an address and confirms it, the *same*
person gains an `Identity` and a `PatientUser`, `identified_at` is stamped, and from that moment they
are an ordinary PRomop patient. No answer moves, no row is re-parented, and no second person appears
— which is what CON-4 asks for.

**4. There is a rule for the collision, and it is not "re-point".** If the confirmed address already
resolves to a *different* person, `resolve_or_create_person` would today return that person and
re-point its `PatientUser` (`services.py:141-163`). Under CON-4 that would leave the account on one
person and the answers on another; `PatientUser` is one-to-one on both sides, so it cannot be on
both. **Merging two patient records is a clinical-safety operation, not a survey side effect.** So:
the response stays bound to the person it was minted with, a merge candidate is recorded for a human
or a separate reconciliation path, and nothing is silently attached to a stranger. This should be
added to the open decisions in [`requirements.md`](requirements.md); it is the likeliest case in a
population that already uses the portal.

### Lifecycle

Eager creation (open decision #5) keeps the FK non-null everywhere, at the cost of a person per
abandoned attempt on a public endpoint. Three things bound that cost:

- **Throttling.** Response creation is already rate-limited per hashed client key; that limit is now
  also the rate at which a stranger can mint rows in PRomop, and should be read that way when it is
  set.
- **Purging.** `purge_abandoned_responses` extends to delete the person too, when it is marked, still
  unidentified, has no clinical rows, and its last response has gone.
- **Counting.** The marker keeps them out of every patient count from the day they first exist,
  rather than after someone notices.

### Considered and rejected

- **One shared sentinel person for unclaimed responses.** Keeps the FK non-null with a single row, but
  every unclaimed response then belongs to the same "patient", which is worse than the problem: no
  response can ever be promoted, and any query grouping by person is wrong.
- **Creating the person lazily, at submission.** Cheapest in rows, but the FK is null for the entire
  time a participant is answering — which is precisely the invariant DEP-2 and RUN-2 exist to
  establish, and the window in which most abandonment happens anyway.

---

## M4 — Retire the standalone profile

Last, because everything above must work first.

- Remove `PROLOG_PROFILE`, `prolog/settings_dev.py`, the profile validation in `conf.py`, and the
  second CI job. The app's own test harness keeps pointing `PROLOG_PARTICIPANT_MODEL` at `auth.User`
  — a fixture so the suite runs without PRomop's schema, not a deployment profile.
- Delete `docker/`, `docker-compose.yml` and the standalone deployment path.
- Rewrite [`deployment.md`](deployment.md) and [`integration.md`](integration.md) for the PRomop
  shape and drop their direction-of-travel banners.
- Retire the FLF deployment: its Terraform, its image, and the Render resources they created.

---

## Deferred, deliberately

- **Clinical meaning of answers (DEP-7).** Answers stay in the survey tables. PRomop has no
  `survey_conduct` table and no FHIR `Questionnaire`/`QuestionnaireResponse`, and the survey-to-OMOP
  mapping is a "coming soon" card (PRomop #902, #903). When it is built, one existing constraint
  applies: wearable-style provenance types rows 32865 "Patient self-report", never 32883 "Survey",
  after that mislabelling caused a real defect.
- **PRomop's existing survey feature is to be retired** (open decision 9, 2026-09-02). `Survey` and
  `PatientSurveyResponse` shipped as PHR-S FM phase 4a; PROlog replaces them. That is an M5 in its
  own right and blocks nothing in M0–M4, but it has two parts that need planning rather than
  discovering: existing responses need a migration path — the two models do not have the same shape,
  since PRomop's is a flat `values` map against a mutable template and PROlog's is answer rows
  against an immutable version — and PRomop's **PH.2.1 conformance claim** currently rests on the
  feature being retired, so it has to be re-examined against this one before the claim is restated.

---

## Order and gating

| Phase | Gates | Blocked by |
| --- | --- | --- |
| **M0** pins | everything | nothing — start here |
| **M1** app wiring | M2 | M0 |
| **M2** tables | non-null FK | M1, and M3 for the FK itself |
| **M3** RUN-2 | the non-null FK, CON-4 | M1 — *host primitive and binding done; the FK flip remains* |
| **M4** retire standalone | nothing | M0–M3 in production |
