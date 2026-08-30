"""Phase 7: integrated profile — participant link, identity capture, account resume.

Runs only with PROLOG_PROFILE=integrated PROLOG_PARTICIPANT_MODEL=auth.User
(and --no-migrations, since the participant column is added by the host's
migration). CI runs this configuration as a separate job.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from prolog_surveys import conf
from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.models import SurveyResponse
from prolog_surveys.tests import fake_identity

pytestmark = pytest.mark.skipif(not conf.is_integrated(), reason="integrated profile only")

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = REPO_ROOT / "examples" / "sample-wellbeing.json"


def definition(**changes):
    doc = json.loads(EXAMPLE.read_text())
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
