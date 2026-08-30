"""Phase 7: integrated profile — participant link, identity capture, account resume.

Runs only with PROLOG_PROFILE=integrated PROLOG_PARTICIPANT_MODEL=auth.User;
the packaged ``0005_participant`` migration adds the participant columns when
that setting is present. CI runs this configuration as a separate job.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model

from prolog_surveys import conf
from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.models import SurveyResponse
from prolog_surveys.tests import fake_identity
from prolog_surveys.tests.conftest import example_definition

pytestmark = pytest.mark.skipif(not conf.is_integrated(), reason="integrated profile only")


def definition(**changes):
    doc = example_definition()
    doc.update(changes)
    return doc


@pytest.fixture
def identity_service(settings):
    settings.PROLOG_IDENTITY_SERVICE = "prolog_surveys.tests.fake_identity.FakeIdentityService"
    fake_identity.CALLS.clear()
    return fake_identity


@pytest.fixture
def linked_definition():
    doc = definition()
    for s in doc["sections"]:
        for q in s["questions"]:
            if q["type"] == "email":
                q["config"] = {"link_identity": True}
    return doc


@pytest.mark.django_db
def test_participant_field_exists():
    assert any(f.name == "participant" for f in SurveyResponse._meta.get_fields())


@pytest.mark.django_db
def test_identity_capture_links_participant(api_client, identity_service, linked_definition):
    load_definition(linked_definition, activate=True)
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    r = api_client.post(
        f"/api/run/responses/{rid}/identity/", {"email": "someone@example.org"}, format="json"
    )
    assert r.status_code == 204
    response = SurveyResponse.objects.get(pk=rid)
    assert response.participant is not None and response.identity_linked_at is not None
    assert response.answers.get(question_key="contact_email").value == {"provided": True}
    assert identity_service.CALLS[0].email == "someone@example.org"
    # idempotent: a retry does not create a second participant
    api_client.post(
        f"/api/run/responses/{rid}/identity/", {"email": "someone@example.org"}, format="json"
    )
    assert len(identity_service.CALLS) == 1
    # the email is nowhere in PROlog's tables or API
    body = api_client.get(f"/api/run/responses/{rid}/").json()
    assert "someone" not in json.dumps(body)
    assert not get_user_model().objects.filter(email__contains="someone").exists()


@pytest.mark.django_db
def test_identity_failure_leaves_response_anonymous(
    api_client, identity_service, linked_definition
):
    load_definition(linked_definition, activate=True)
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    r = api_client.post(
        f"/api/run/responses/{rid}/identity/", {"email": "x@fail.example"}, format="json"
    )
    assert r.status_code == 503
    response = SurveyResponse.objects.get(pk=rid)
    assert response.participant is None
    assert not response.answers.filter(question_key="contact_email").exists()


@pytest.mark.django_db
def test_identity_unwrapped_exception_is_503_not_500(
    api_client, identity_service, linked_definition
):
    """A host service that lets a transport error escape must not turn into a
    500 (whose error report would carry the address)."""
    load_definition(linked_definition, activate=True)
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    r = api_client.post(
        f"/api/run/responses/{rid}/identity/", {"email": "x@crash.example"}, format="json"
    )
    assert r.status_code == 503
    assert SurveyResponse.objects.get(pk=rid).participant is None


@pytest.mark.django_db
def test_identity_requires_link_identity_question(api_client, identity_service):
    load_definition(definition(), activate=True)  # store_separately, not link_identity
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    assert (
        api_client.post(
            f"/api/run/responses/{rid}/identity/", {"email": "a@b.co"}, format="json"
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_account_survey_resume_and_ownership(api_client):
    doc = definition(participation={"anonymous": False, "resume": "account"})
    load_definition(doc, activate=True)
    alice = get_user_model().objects.create_user("alice", "", "x")
    bob = get_user_model().objects.create_user("bob", "", "x")
    api_client.force_authenticate(alice)
    r = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    assert r.status_code == 201
    rid = r.json()["id"]
    assert SurveyResponse.objects.get(pk=rid).participant == alice
    # creating again resumes the in-progress response
    r = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    assert r.status_code == 200 and r.json()["id"] == rid
    # another account cannot touch it
    api_client.force_authenticate(bob)
    assert api_client.get(f"/api/run/responses/{rid}/").status_code == 403
    assert (
        api_client.put(
            f"/api/run/responses/{rid}/answers/age_band/",
            {"value": {"option": "30_49"}},
            format="json",
        ).status_code
        == 403
    )
    api_client.force_authenticate(None)
    assert api_client.get(f"/api/run/responses/{rid}/").status_code == 403


@pytest.mark.django_db
def test_reconsent_required_for_new_version(api_client):
    doc = definition(
        participation={"anonymous": False, "resume": "account"},
        consent={"version": "v1", "text": {"en": "one", "es": "u", "fr": "u"}},
    )
    load_definition(doc, activate=True)
    alice = get_user_model().objects.create_user("alice", "", "x")
    api_client.force_authenticate(alice)
    r = api_client.post(
        "/api/run/responses/",
        {
            "slug": "sample-wellbeing",
            "language": "en",
            "consent": {"version": "v1", "agreed": True},
        },
        format="json",
    )
    assert r.status_code == 201
    api_client.post(
        f"/api/run/responses/{r.json()['id']}/submit/"
    )  # will 400 (missing) but that is fine here
    doc["version"] = "2.0"
    doc["consent"] = {"version": "v2", "text": {"en": "two", "es": "d", "fr": "d"}}
    load_definition(doc, activate=True)
    r = api_client.post(
        "/api/run/responses/",
        {
            "slug": "sample-wellbeing",
            "language": "en",
            "consent": {"version": "v1", "agreed": True},
        },
        format="json",
    )
    assert r.status_code == 400 and "consent" in r.json()
    r = api_client.post(
        "/api/run/responses/",
        {
            "slug": "sample-wellbeing",
            "language": "en",
            "consent": {"version": "v2", "agreed": True},
        },
        format="json",
    )
    assert r.status_code == 201


@pytest.mark.django_db
def test_invited_account_participant_starts_each_administration(api_client):
    """A logged-in invited participant's older in-progress response must not
    stand in for a new administration (repeat surveys, RUN-5)."""
    import datetime as dt

    from prolog_surveys.invitations import schedule_due
    from prolog_surveys.models import SurveyInvitation

    doc = definition(
        participation={
            "anonymous": False,
            "resume": "account",
            "repeat": {"every": 1, "unit": "months", "start_date": "2026-01-01"},
        }
    )
    version = load_definition(doc, activate=True).version
    user = get_user_model().objects.create_user("p", "p@example.org", "x")
    invitation = SurveyInvitation.objects.create(
        survey=version.survey, email="p@example.org", participant=user
    )
    (january,) = schedule_due(dt.date(2026, 1, 15))
    (february,) = schedule_due(dt.date(2026, 2, 15))
    api_client.force_authenticate(user)
    start = lambda admin: api_client.post(  # noqa: E731
        "/api/run/responses/",
        {"slug": "sample-wellbeing", "language": "en", "invitation": str(admin.id)},
        format="json",
    )
    r1 = start(january)
    assert r1.status_code == 201 and r1.json()["administration"] == str(january.id)
    r2 = start(february)
    assert r2.status_code == 201 and r2.json()["administration"] == str(february.id)
    assert r2.json()["id"] != r1.json()["id"]
    assert start(february).json()["id"] == r2.json()["id"]  # the link resumes its own
    assert invitation.administrations.count() == 2


@pytest.mark.django_db
def test_deactivated_invitation_keeps_the_account_participant_in(api_client):
    """Deactivating an invitation revokes the *links* it sent; the invited
    participant, signed in to their account, keeps their own response
    (otherwise account resume would keep handing back a response they can
    no longer open)."""
    from prolog_surveys.models import SurveyAdministration, SurveyInvitation

    doc = definition(participation={"anonymous": False, "resume": "account"})
    version = load_definition(doc, activate=True).version
    user = get_user_model().objects.create_user("p", "p@example.org", "x")
    invitation = SurveyInvitation.objects.create(
        survey=version.survey, email="p@example.org", participant=user
    )
    administration = SurveyAdministration.objects.create(
        invitation=invitation, survey_version=version, due_at="2026-01-01"
    )
    start = lambda **extra: api_client.post(  # noqa: E731
        "/api/run/responses/",
        {"slug": "sample-wellbeing", "language": "en", **extra},
        format="json",
    )
    api_client.force_authenticate(user)
    r = start(invitation=str(administration.id))
    assert r.status_code == 201, r.content
    rid = r.json()["id"]
    invitation.active = False
    invitation.save()
    # The link itself is dead, for the account holder and for anyone else.
    assert start(invitation=str(administration.id)).status_code == 403
    api_client.force_authenticate(None)
    assert api_client.get(f"/api/run/responses/{rid}/").status_code == 403
    assert api_client.get(f"/api/run/surveys/sample-wellbeing/?response={rid}").status_code == 403
    # The participant's own access is untouched.
    api_client.force_authenticate(user)
    assert api_client.get(f"/api/run/responses/{rid}/").status_code == 200
    assert api_client.get(f"/api/run/surveys/sample-wellbeing/?response={rid}").status_code == 200
    r = api_client.patch(
        f"/api/run/responses/{rid}/", {"last_question_key": "country"}, format="json"
    )
    assert r.status_code == 200
    r = api_client.put(
        f"/api/run/responses/{rid}/answers/country/", {"value": {"option": "GB"}}, format="json"
    )
    assert r.status_code == 200
    assert start().status_code == 200 and start().json()["id"] == rid  # account resume
    r = api_client.post(f"/api/run/responses/{rid}/submit/")
    assert r.status_code == 400 and "missing" in r.json()  # reachable, just incomplete
    # Another account still cannot touch it.
    api_client.force_authenticate(get_user_model().objects.create_user("other", "", "x"))
    assert api_client.get(f"/api/run/responses/{rid}/").status_code == 403


class LockProbeService:
    """Identity service that checks, from a second connection, whether the
    caller holds the response row lock while it runs."""

    row_locked: bool | None = None

    def create_or_link(self, request):
        from django.db import OperationalError, connections

        conn = connections.create_connection("default")
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(f"SELECT id FROM {SurveyResponse._meta.db_table} FOR UPDATE NOWAIT")
                    cur.fetchall()
                    LockProbeService.row_locked = False
                except OperationalError:
                    LockProbeService.row_locked = True
        finally:
            conn.close()
        user, _ = get_user_model().objects.get_or_create(username="probe")
        from prolog_surveys.identity import IdentityResult

        return IdentityResult(participant_pk=user.pk)


@pytest.mark.django_db(transaction=True)
def test_identity_service_is_called_without_the_response_lock(
    api_client, settings, linked_definition
):
    """The host's service is an out-of-process call of unknown latency: it
    must not pin the response row lock (and the connection) for its duration,
    or every concurrent autosave for that response queues behind it."""
    settings.PROLOG_IDENTITY_SERVICE = f"{__name__}.LockProbeService"
    LockProbeService.row_locked = None
    load_definition(linked_definition, activate=True)
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    r = api_client.post(
        f"/api/run/responses/{rid}/identity/", {"email": "someone@example.org"}, format="json"
    )
    assert r.status_code == 204, r.content
    assert LockProbeService.row_locked is False
    response = SurveyResponse.objects.get(pk=rid)
    assert response.participant is not None and response.identity_linked_at is not None
    assert response.answers.get(question_key="contact_email").value == {"provided": True}
