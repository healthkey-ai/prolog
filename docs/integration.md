# Installing PROlog in a host platform

> **Design revision 2026-08-31.** This is no longer one profile among two — it
> is how PROlog is deployed. **PRomop owns the database**; PROlog contributes
> its tables to PRomop's schema and holds nothing of its own. Every response is
> bound to a `Person` (created without identifying attributes when the
> participant is not signed in), and identity capture creates a real account for
> that person rather than a separate contact row. See
> [requirements.md](requirements.md) "Changes in this revision"; the
> settings and migration mechanics below are unchanged by it.

**Requirements:** DEP-1, DEP-2, DEP-7, CON-1, CON-2, CON-4, CON-7, CON-8, RUN-2, RUN-3, RUN-5. Operating a deployment: [deployment.md](deployment.md).

In the integrated profile the `prolog_surveys` app is installed inside a
host Django project (for example PRomop) that provides participant
identity. PROlog then links responses to the host's participant model,
can turn a consented email into a participant record through the host's
identity service, resumes account surveys per participant, and runs
invitations/repeat administration.

## Host project settings

```python
INSTALLED_APPS += ["rest_framework", "corsheaders", "prolog_surveys"]

PROLOG_PROFILE = "integrated"
PROLOG_PARTICIPANT_MODEL = "omop_core.Person"          # any "app_label.Model"
PROLOG_PARTICIPANT_RESOLVER = "myhost.prolog.resolve_participant"  # (request) -> pk | None
PROLOG_IDENTITY_SERVICE = "myhost.prolog.IdentityService"          # class or factory
PROLOG_DEFINITION_DIRS = ["/srv/surveys"]
PROLOG_THEME_DIRS = ["/srv/prolog/themes", "/srv/themes"]
PROLOG_SCHEMA_DIR = "/srv/prolog/schema"
PROLOG_PUBLIC_URL = "https://surveys.example.org"
PROLOG_EMAIL_FROM = "surveys@example.org"
PROLOG_CLIENT_KEY_SALT = "<a long random secret>"  # hashes client keys for throttling; defaults to SECRET_KEY when unset
REST_FRAMEWORK = {
    ...,
    # Throttle scopes (defaults in prolog_surveys.conf.THROTTLE_RATES apply when omitted)
    "DEFAULT_THROTTLE_RATES": {"run.read": "1200/hour", "run.create": "30/hour", "run.capture": "30/hour", "run.answer": "600/hour", "run.write": "3000/hour"},
    "NUM_PROXIES": 1,  # reverse proxies whose X-Forwarded-For is trusted for the client address
}
```

`urls.py`: `path("api/", include("prolog_surveys.urls"))` and, if the host
serves the runner, the catch-all `runner_index` view.

The host project's `TIME_ZONE` governs every calendar date the app takes:
a survey's `effective_from`/`effective_to`, the due dates of repeat
schedules and the daily `send_due_invitations` cycle, and contacts'
`captured_on`. Set it to the deployment's local zone.

### CSRF

Session-authenticated participants (account surveys) write through the
runner, which reads Django's `csrftoken` cookie and echoes it in the
`X-CSRFToken` header. Keep the defaults that make this work:
`CSRF_COOKIE_HTTPONLY = False`, `CSRF_USE_SESSIONS = False`, and the
default `CSRF_COOKIE_NAME` / `CSRF_HEADER_NAME`. Anonymous and invited
participants are not session-authenticated and need no token.

## Migrations (DEP-2)

The participant foreign keys (`SurveyResponse.participant`,
`SurveyInvitation.participant`) target a model only the host knows, so the
packaged migration `0005_participant` builds its operations from
`PROLOG_PARTICIPANT_MODEL` at load time: with the setting present it adds
the two columns (and depends on the participant model's app); without it,
it is empty. Set the setting **before** the first `migrate` and simply run:

```sh
python manage.py migrate
```

No `makemigrations` in the host project and no `MIGRATION_MODULES` are
needed. The fields exist on the models only when `PROLOG_PARTICIPANT_MODEL`
is set, so the standalone schema and the integrated schema differ by exactly
these two columns; `makemigrations --check` passes in both profiles.
The dependency is the participant app's *first* migration (the same
convention as `AUTH_USER_MODEL`), so the participant model must exist from
that migration on.

Switching the profile *after* `migrate` leaves `0005_participant` recorded
as applied while the participant columns are missing. The database system
check `prolog_surveys.E002` detects that and fails `migrate` /
`check --database default` with the remedy: `migrate prolog_surveys 0004
--fake --skip-checks`, then `migrate` again.

## Participant resolver (account surveys, RUN-3)

For surveys with `participation.anonymous = false`, PROlog needs the
participant behind an authenticated request:

```python
def resolve_participant(request):
    user = request.user
    return user.person_id if user.is_authenticated else None
```

With `resume: "account"`, `POST /api/run/responses/` returns the
participant's in-progress response for the active version instead of
creating another; reads and writes are refused for anyone else (403).
Without a resolver, PROlog uses `request.user.pk` when the participant
model *is* `AUTH_USER_MODEL`.

## Identity service (CON-4)

For anonymous surveys whose email question sets `"link_identity": true`,
the runner posts the consented address to
`POST /api/run/responses/{id}/identity/`. PROlog forwards it — and nothing
else — to your service:

```python
from prolog_surveys.identity import IdentityRequest, IdentityResult, IdentityServiceError

class IdentityService:
    def create_or_link(self, request: IdentityRequest) -> IdentityResult:
        # request.email, request.idempotency_key (stable per response),
        # request.participant_pk (the Person the response is already bound to),
        # request.survey_slug, request.language
        account = create_or_find_account(email=request.email,
                                         person_id=request.participant_pk,
                                         idempotency_key=request.idempotency_key)
        return IdentityResult(participant_pk=account.person_id)
```

In PRomop this creates an `Identity` and a `PatientUser` for the existing
`Person`, promoting it from unidentified to identified **in place** — no answer
is re-parented and no second person record appears. Returning a different
`participant_pk` than the one passed in means the host matched the address to an
existing person; PROlog re-points the response, which is the one case where a
response changes hands. Treat a freshly created account's address as unverified
until confirmed and expose no pre-existing data to it before then (requirements
open decision #6): a participant can always mistype, or type, someone else's
address.

Guarantees: the email is never written to any PROlog table, log or API
payload; the call is idempotent per response (a retry reuses the same
key); on `IdentityServiceError` — or any other exception your service lets
escape — the endpoint answers 503 and the response stays anonymous; on success `participant` and `identity_linked_at` are set
and the answer row records only `{"provided": true}`. Mapping execution
(Phase 9) runs after this link exists.

## Consent (CON-1, CON-2)

A definition with `consent` requires `{"version", "agreed": true}` when a
response is created and stores a `SurveyConsent` attestation (version,
text hash, language, timestamp). Because every administration creates a
new response against a specific version, a changed consent version is
re-presented automatically; an existing submitted response's consent is
never altered.

## Invitations and repeat administration (RUN-5)

- Create `SurveyInvitation` rows (admin or your own code) with a
  participant and/or an email, optionally a language.
- `participation.repeat` in the definition (`every`, `unit`, `start_date`,
  optional `end_date`, `use_current_version`) drives the schedule; without
  it, each invitation is administered once.
- Run `manage.py send_due_invitations` daily (cron/Celery beat). It creates
  the due `SurveyAdministration` rows and emails
  `PROLOG_PUBLIC_URL/s/<slug>?invite=<administration id>` using the
  `prolog_surveys/email/invitation.{txt,html}` templates (override them in
  the host project to brand them). Runs are serialised with a PostgreSQL
  advisory lock: a second run started while one is in progress exits with
  a notice and sends nothing.
- The administration id in the link is the credential: it opens the
  survey, creates the response bound to the scheduled (or then-active)
  version and the invited participant, and re-opening the link resumes it.
  Each administration yields a distinct response, preserving history.
- To withdraw an invitation, set `active = False` (admin or code): its links
  stop opening the survey and the responses they started become
  inaccessible to the link holder (403). An invited participant who is
  signed in keeps (and, with `resume: "account"`, resumes) their own
  response; only the links are revoked. Prefer that over deleting the
  invitation, which cascades to its administrations and leaves any
  in-progress response orphaned (unlinked, but still stored until the
  abandoned-response purge).

## Testing the integrated profile

```sh
POSTGRES_DB=prolog_integrated PROLOG_PROFILE=integrated PROLOG_PARTICIPANT_MODEL=auth.User \
  uv run pytest --create-db
```

The packaged migrations (including `0005_participant`) build the schema, so
the chain is exercised exactly as a host would run it; a separate database
name keeps it apart from the standalone test database. CI runs both
configurations.
