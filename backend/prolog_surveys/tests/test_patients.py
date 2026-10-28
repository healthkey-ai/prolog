"""Patient linkage using auth.User as the host-owned patient fixture.

Run with PROLOG_PATIENT_MODEL=auth.User. This exercises a real foreign key,
submission rollback and deletion without importing PRomop's clinical schema.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from prolog_surveys import conf
from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.models import ResponseStatus, SurveyAnswer, SurveyLinkedContact
from prolog_surveys.patients import link_submitted_response
from prolog_surveys.tests.conftest import make_response

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        conf.patient_model() != "auth.User", reason="requires the patient-model harness"
    ),
]
CALLS = []


def fake_linker(response, contact):
    CALLS.append((response.pk, contact.email))
    patient, _ = get_user_model().objects.get_or_create(
        username=contact.email.casefold(), defaults={"email": contact.email}
    )
    return patient


def failing_linker(response, contact):
    raise RuntimeError(f"sensitive email: {contact.email}")


@pytest.fixture
def attempt(example, settings):
    settings.PROLOG_PATIENT_LINKER = "prolog_surveys.tests.test_patients.fake_linker"
    CALLS.clear()
    # An instrument with only the linked-contact question, all optional.
    email = next(q for s in example["sections"] for q in s["questions"] if q["type"] == "email")
    email["required"] = False
    email["config"].pop("store_separately", None)
    email["config"]["link_response"] = True
    example["sections"] = [{"key": "contact", "title": {"en": "Contact"}, "questions": [email]}]
    version = load_definition(example, activate=True).version
    response = make_response(version, language="en")
    contact = SurveyLinkedContact.objects.create(response=response, email="person@example.org")
    SurveyAnswer.objects.create(
        response=response, question_key=email["key"], value={"provided": True}
    )
    return response, contact


def test_submission_links_patient_only_at_completion(api_client, attempt):
    response, contact = attempt
    assert link_submitted_response(response) is None
    assert CALLS == []
    result = api_client.post(f"/api/run/responses/{response.pk}/submit/")
    assert result.status_code == 200, result.content
    contact.refresh_from_db()
    response.refresh_from_db()
    assert contact.patient.email == contact.email
    assert response.submitted_at is not None
    assert len(CALLS) == 1
    # Only staff-side linkage; no patient key or address leaks to the runner.
    assert "patient" not in json.dumps(result.json())
    assert "person@example.org" not in json.dumps(result.json())
    assert api_client.post(f"/api/run/responses/{response.pk}/submit/").status_code == 409
    link_submitted_response(response)
    assert len(CALLS) == 1


def test_failure_rolls_back_submission_and_hides_email(api_client, attempt, settings, caplog):
    response, contact = attempt
    settings.PROLOG_PATIENT_LINKER = "prolog_surveys.tests.test_patients.failing_linker"
    result = api_client.post(f"/api/run/responses/{response.pk}/submit/")
    assert result.status_code == 500
    assert contact.email not in result.content.decode() + caplog.text
    response.refresh_from_db()
    contact.refresh_from_db()
    assert response.status == ResponseStatus.IN_PROGRESS
    assert response.submitted_at is None and contact.patient_id is None
    settings.PROLOG_PATIENT_LINKER = "prolog_surveys.tests.test_patients.fake_linker"
    assert api_client.post(f"/api/run/responses/{response.pk}/submit/").status_code == 200


def test_no_linked_contact_never_calls_host(api_client, attempt):
    response, contact = attempt
    contact.delete()
    assert api_client.post(f"/api/run/responses/{response.pk}/submit/").status_code == 200
    assert CALLS == []


def test_patient_deletion_sets_null_and_keeps_survey(attempt):
    response, contact = attempt
    response.status = ResponseStatus.SUBMITTED
    response.submitted_at = timezone.now()
    response.save()
    patient = link_submitted_response(response)
    patient.delete()
    contact.refresh_from_db()
    assert contact.patient_id is None
    assert contact.response_id == response.pk


def test_existing_email_reuses_patient(attempt):
    response, contact = attempt
    existing = get_user_model().objects.create(username=contact.email, email=contact.email)
    response.status = ResponseStatus.SUBMITTED
    response.submitted_at = timezone.now()
    response.save()
    assert link_submitted_response(response).pk == existing.pk
