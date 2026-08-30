# Integrated profile (installing PROlog in a host platform)

**Requirements:** DEP-1, DEP-2, CON-1, CON-2, CON-4, RUN-3, RUN-5. Standalone deployment is described in [deployment.md](deployment.md).

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
REST_FRAMEWORK = {
    ...,
    # Throttle scopes (defaults in prolog_surveys.conf.THROTTLE_RATES apply when omitted)
    "DEFAULT_THROTTLE_RATES": {"run.read": "1200/hour", "run.create": "30/hour", "run.capture": "30/hour", "run.answer": "600/hour"},
    "NUM_PROXIES": 1,  # reverse proxies whose X-Forwarded-For is trusted for the client address
}
```

`urls.py`: `path("api/", include("prolog_surveys.urls"))` and, if the host
serves the runner, the catch-all `runner_index` view.

## Migrations (DEP-2)

PROlog's own migrations create every table **without** the participant
foreign keys, because the target model is only known to the host. After
installing the app, generate one migration in the host project:

```sh
python manage.py makemigrations prolog_surveys   # adds SurveyResponse.participant and SurveyInvitation.participant
```

Keep that migration in the host repository (set `MIGRATION_MODULES` if you
prefer to keep it out of the installed package). The fields exist on the
models only when `PROLOG_PARTICIPANT_MODEL` is set, so the standalone
schema and the integrated schema differ by exactly these two columns.

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
        # request.email, request.idempotency_key (stable per response), request.survey_slug, request.language
        person = create_or_find_person(email=request.email, idempotency_key=request.idempotency_key)
        return IdentityResult(participant_pk=person.pk)
```

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
  the host project to brand them).
- The administration id in the link is the credential: it opens the
  survey, creates the response bound to the scheduled (or then-active)
  version and the invited participant, and re-opening the link resumes it.
  Each administration yields a distinct response, preserving history.

## Testing the integrated profile

```sh
POSTGRES_DB=prolog_integrated PROLOG_PROFILE=integrated PROLOG_PARTICIPANT_MODEL=auth.User \
  uv run pytest --no-migrations --create-db
```

`--no-migrations` builds the schema from the models (including the
participant columns) and a separate database name keeps it apart from the
standalone test database. CI runs both configurations.
