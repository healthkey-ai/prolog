"""Phase 2: runner API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.models import SurveyAnswer, SurveyConsent, SurveyContact, SurveyResponse

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = REPO_ROOT / "examples" / "sample-wellbeing.json"


@pytest.fixture
def definition() -> dict:
    return json.loads(EXAMPLE.read_text())


@pytest.fixture
def active(db, definition):
    return load_definition(definition, activate=True).version


@pytest.fixture
def response_id(api_client, active):
    r = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    assert r.status_code == 201, r.content
    return r.json()["id"]


def put_answer(api_client, response_id, key, value):
    return api_client.put(
        f"/api/run/responses/{response_id}/answers/{key}/", {"value": value}, format="json"
    )


# --- definition ---------------------------------------------------------------


def test_definition_localized_with_etag(api_client, active):
    r = api_client.get("/api/run/surveys/sample-wellbeing/?lang=es")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Chequeo de bienestar"
    assert body["language"] == "es"
    assert body["theme_code"] == "default"
    assert "notes" not in body
    assert body["sections"][0]["questions"][2]["options"][0]["label"] == "Menos de 30"
    etag = r.headers["ETag"]
    assert (
        api_client.get(
            "/api/run/surveys/sample-wellbeing/?lang=es", HTTP_IF_NONE_MATCH=etag
        ).status_code
        == 304
    )
    assert api_client.get("/api/run/surveys/sample-wellbeing/?lang=xx").json()["language"] == "en"


def test_definition_404_when_not_active(api_client, db, definition):
    load_definition(definition)  # draft only
    assert api_client.get("/api/run/surveys/sample-wellbeing/").status_code == 404
    assert api_client.get("/api/run/surveys/nope/").status_code == 404


def test_effective_dates(api_client, active):
    survey = active.survey
    survey.effective_to = "2000-01-01"
    survey.save()
    assert api_client.get("/api/run/surveys/sample-wellbeing/").status_code == 404


def test_options_source(api_client, active):
    r = api_client.get("/api/run/options/iso3166_countries/?lang=fr")
    assert r.status_code == 200
    assert any(o["key"] == "DE" and o["label"] == "Allemagne" for o in r.json()["options"])
    assert api_client.get("/api/run/options/planets/").status_code == 404


# --- responses ------------------------------------------------------------------


def test_create_response_validates_language(api_client, active):
    r = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "de"}, format="json"
    )
    assert r.status_code == 400


def test_account_survey_requires_authentication(api_client, db, definition):
    definition["participation"] = {"anonymous": False}
    load_definition(definition, activate=True)
    assert api_client.get("/api/run/surveys/sample-wellbeing/").status_code == 403
    r = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    assert r.status_code == 403
    # Standalone has no participant model, so an authenticated user still cannot
    # be linked to a response; refusing here beats creating an unreadable one.
    # In the integrated profile (participant model = auth.User) the same user
    # resolves to a participant and is let in.
    from prolog_surveys import conf

    expected = 200 if conf.is_integrated() else 403
    user = get_user_model().objects.create_user("p", "p@example.org", "x")
    api_client.force_authenticate(user)
    assert api_client.get("/api/run/surveys/sample-wellbeing/").status_code == expected
    r = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    assert r.status_code == (201 if conf.is_integrated() else 403)


def test_consent_required_and_recorded(api_client, db, definition):
    definition["consent"] = {
        "version": "2026-01",
        "text": {"en": "We store answers.", "es": "x", "fr": "y"},
    }
    load_definition(definition, activate=True)
    r = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    assert r.status_code == 400 and "consent" in r.json()
    r = api_client.post(
        "/api/run/responses/",
        {
            "slug": "sample-wellbeing",
            "language": "en",
            "consent": {"version": "2026-01", "agreed": True},
        },
        format="json",
    )
    assert r.status_code == 201
    consent = SurveyConsent.objects.get(response_id=r.json()["id"])
    assert consent.consent_version == "2026-01"


def test_get_response_payload(api_client, response_id):
    body = api_client.get(f"/api/run/responses/{response_id}/").json()
    assert body["status"] == "in_progress"
    assert body["answers"] == {}
    assert body["visible"][0] == "welcome"
    assert "symptoms" not in body["visible"]
    assert body["progress"] == {"answered": 0, "total": 11}
    assert body["slug"] == "sample-wellbeing" and body["version"] == "1.0"


def test_patch_progress_and_language(api_client, response_id):
    r = api_client.patch(
        f"/api/run/responses/{response_id}/",
        {"last_question_key": "overall", "language": "es"},
        format="json",
    )
    assert r.status_code == 200
    assert r.json()["last_question_key"] == "overall" and r.json()["language"] == "es"
    assert (
        api_client.patch(
            f"/api/run/responses/{response_id}/", {"language": "de"}, format="json"
        ).status_code
        == 400
    )


# --- answers ---------------------------------------------------------------------


def test_answer_upsert_and_cascade(api_client, response_id):
    r = put_answer(api_client, response_id, "has_symptoms", {"option": "yes"})
    assert r.status_code == 200
    assert "symptoms" in r.json()["visible"]
    r = put_answer(api_client, response_id, "symptoms", {"options": ["fatigue", "worry"]})
    assert r.json()["invalidated"] == []
    r = put_answer(
        api_client, response_id, "symptom_impact", {"ratings": {"fatigue": 1, "worry": 2}}
    )
    assert r.status_code == 200
    # gate change prunes the matrix then removes everything downstream
    r = put_answer(api_client, response_id, "symptoms", {"options": ["worry"]})
    assert r.json()["invalidated"] == ["symptom_impact"]
    assert SurveyAnswer.objects.get(
        response_id=response_id, question_key="symptom_impact"
    ).value == {"ratings": {"worry": 2}}
    r = put_answer(api_client, response_id, "has_symptoms", {"option": "no"})
    assert r.json()["invalidated"] == ["symptoms", "symptom_impact"]
    assert not SurveyAnswer.objects.filter(
        response_id=response_id, question_key__in=["symptoms", "symptom_impact"]
    ).exists()
    assert SurveyAnswer.objects.get(
        response_id=response_id, question_key="has_symptoms"
    ).option_keys == ["no"]
    assert SurveyResponse.objects.get(pk=response_id).last_question_key == "has_symptoms"


def test_answer_validation_errors(api_client, response_id):
    r = put_answer(api_client, response_id, "overall", {"value": 9})
    assert r.status_code == 400 and "value" in r.json()
    assert (
        put_answer(api_client, response_id, "symptoms", {"options": ["pain"]}).status_code == 400
    )  # hidden
    assert put_answer(api_client, response_id, "ghost", {"option": "x"}).status_code == 404
    assert put_answer(api_client, response_id, "welcome", {"text": "x"}).status_code == 400
    assert (
        put_answer(api_client, response_id, "contact_email", {"provided": True}).status_code == 400
    )
    assert (
        api_client.put(
            f"/api/run/responses/{response_id}/answers/overall/", {"nope": 1}, format="json"
        ).status_code
        == 400
    )


def test_dropdown_accepts_iso_code_and_inline_option(api_client, response_id):
    assert put_answer(api_client, response_id, "country", {"option": "GB"}).status_code == 200
    assert (
        put_answer(api_client, response_id, "country", {"option": "prefer_not_to_say"}).status_code
        == 200
    )
    assert put_answer(api_client, response_id, "country", {"option": "ZZ"}).status_code == 400


def complete(api_client, response_id):
    steps = [
        ("country", {"option": "GB"}),
        ("age_band", {"option": "30_49"}),
        ("birth_year", {"skipped": True}),
        ("last_visit", {"skipped": True}),
        ("overall", {"value": 4}),
        ("has_symptoms", {"option": "no"}),
        ("daily_activities", {"ratings": {"walking": 2, "housework": 1, "socialising": 3}}),
        ("outcome_ranking", {"order": ["energy", "independence", "side_effects", "fewer_visits"]}),
        ("support_wanted", {"options": ["information"]}),
        ("anything_else", {"skipped": True}),
    ]
    for key, value in steps:
        assert put_answer(api_client, response_id, key, value).status_code == 200, key


def test_submit_requires_every_visible_question(api_client, response_id):
    r = api_client.post(f"/api/run/responses/{response_id}/submit/")
    assert r.status_code == 400
    assert r.json()["missing"][0] == "country"
    complete(api_client, response_id)
    r = api_client.post(f"/api/run/responses/{response_id}/submit/")
    assert r.status_code == 400 and r.json()["missing"] == ["contact_email"]
    put_answer(api_client, response_id, "contact_email", {"provided": False})
    r = api_client.post(f"/api/run/responses/{response_id}/submit/")
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    # read-only afterwards
    assert put_answer(api_client, response_id, "overall", {"value": 1}).status_code == 409
    assert api_client.post(f"/api/run/responses/{response_id}/submit/").status_code == 409
    assert (
        api_client.patch(
            f"/api/run/responses/{response_id}/", {"language": "es"}, format="json"
        ).status_code
        == 409
    )
    assert api_client.get(f"/api/run/responses/{response_id}/").json()["status"] == "submitted"


def test_contact_capture_is_unlinked(api_client, response_id):
    r = api_client.post(
        f"/api/run/responses/{response_id}/contact/",
        {"email": "someone@example.org"},
        format="json",
    )
    assert r.status_code == 204
    contact = SurveyContact.objects.get()
    assert contact.email == "someone@example.org"
    assert "separately" in contact.consent_text
    assert not any(f.name == "response" for f in SurveyContact._meta.get_fields())
    answer = SurveyAnswer.objects.get(response_id=response_id, question_key="contact_email")
    assert answer.value == {"provided": True}
    body = api_client.get(f"/api/run/responses/{response_id}/").json()
    assert "someone" not in json.dumps(body)
    assert (
        api_client.post(
            f"/api/run/responses/{response_id}/contact/", {"email": "nope"}, format="json"
        ).status_code
        == 400
    )


def test_contact_404_without_store_separately(api_client, db, definition):
    for s in definition["sections"]:
        s["questions"] = [q for q in s["questions"] if q["type"] != "email"]
    load_definition(definition, activate=True)
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    assert (
        api_client.post(
            f"/api/run/responses/{rid}/contact/", {"email": "a@b.co"}, format="json"
        ).status_code
        == 404
    )


def test_hard_skip_policy_via_api(api_client, db, definition):
    definition["presentation"] = {"skip_policy": "hard"}
    load_definition(definition, activate=True)
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    assert put_answer(api_client, rid, "age_band", {"skipped": True}).status_code == 400
    assert put_answer(api_client, rid, "birth_year", {"skipped": True}).status_code == 200


def test_no_ip_or_email_persisted(api_client, response_id):
    response = SurveyResponse.objects.get(pk=response_id)
    field_names = {f.name for f in SurveyResponse._meta.get_fields()}
    assert not {"ip", "ip_address", "email"} & field_names
    assert len(response.user_agent_hash) in (0, 64)


def test_consent_not_required_records_only_an_agreement(api_client, db, definition):
    definition["consent"] = {
        "version": "2026-01",
        "required": False,
        "text": {"en": "We store answers.", "es": "x", "fr": "y"},
    }
    load_definition(definition, activate=True)
    r = api_client.post(
        "/api/run/responses/",
        {
            "slug": "sample-wellbeing",
            "language": "en",
            "consent": {"version": "2026-01", "agreed": False},
        },
        format="json",
    )
    assert r.status_code == 201
    assert not SurveyConsent.objects.filter(response_id=r.json()["id"]).exists()
    r = api_client.post(
        "/api/run/responses/",
        {
            "slug": "sample-wellbeing",
            "language": "en",
            "consent": {"version": "old", "agreed": True},
        },
        format="json",
    )
    assert r.status_code == 201
    assert not SurveyConsent.objects.filter(response_id=r.json()["id"]).exists()


def test_contact_capture_is_recorded_once_per_response(api_client, response_id):
    url = f"/api/run/responses/{response_id}/contact/"
    assert api_client.post(url, {"email": "one@example.org"}, format="json").status_code == 204
    # The {provided: true} marker cannot be reset through the answer endpoint...
    r = put_answer(api_client, response_id, "contact_email", {"provided": False})
    assert r.status_code == 200 and r.json()["answer"]["value"] == {"provided": True}
    # ...so a second address is not stored.
    assert api_client.post(url, {"email": "two@example.org"}, format="json").status_code == 204
    assert list(SurveyContact.objects.values_list("email", flat=True)) == ["one@example.org"]


def test_answer_reports_pruned_matrix_rows(api_client, response_id):
    put_answer(api_client, response_id, "has_symptoms", {"option": "yes"})
    put_answer(api_client, response_id, "symptoms", {"options": ["fatigue", "pain"]})
    put_answer(api_client, response_id, "symptom_impact", {"ratings": {"fatigue": 2, "pain": 4}})
    r = put_answer(api_client, response_id, "symptoms", {"options": ["fatigue"]})
    assert r.status_code == 200
    assert r.json()["invalidated"] == ["symptom_impact"]
    assert r.json()["pruned"] == {"symptom_impact": {"ratings": {"fatigue": 2}}}
    # Clearing the source hides the matrix entirely: deleted, not pruned.
    r = put_answer(api_client, response_id, "symptoms", {"skipped": True})
    assert r.json()["invalidated"] == ["symptom_impact"] and r.json()["pruned"] == {}
    assert "symptom_impact" not in r.json()["visible"]


def test_closed_survey_rejects_writes_but_stays_readable(api_client, response_id, active):
    put_answer(api_client, response_id, "country", {"option": "GB"})
    survey = active.survey
    survey.effective_to = "2000-01-01"
    survey.save()
    assert api_client.get(f"/api/run/responses/{response_id}/").status_code == 200
    assert (
        api_client.get(f"/api/run/surveys/sample-wellbeing/?response={response_id}").status_code
        == 200
    )
    r = put_answer(api_client, response_id, "age_band", {"option": "30_49"})
    assert r.status_code == 410 and r.json()["detail"] == "survey has closed"
    for call in (
        lambda: api_client.post(f"/api/run/responses/{response_id}/submit/"),
        lambda: api_client.patch(
            f"/api/run/responses/{response_id}/", {"language": "es"}, format="json"
        ),
        lambda: api_client.post(
            f"/api/run/responses/{response_id}/contact/", {"email": "a@b.co"}, format="json"
        ),
    ):
        assert call().status_code == 410
    survey.effective_to = None
    survey.effective_from = "2999-01-01"
    survey.save()
    r = put_answer(api_client, response_id, "age_band", {"option": "30_49"})
    assert r.status_code == 410 and r.json()["detail"] == "survey is not yet open"


def test_contact_marker_survives_hiding_the_email_question(api_client, db, definition):
    for s in definition["sections"]:
        for q in s["questions"]:
            if q["type"] == "email":
                q["visible_if"] = [{"question": "has_symptoms", "op": "eq", "value": "yes"}]
    load_definition(definition, activate=True)
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    url = f"/api/run/responses/{rid}/contact/"
    assert put_answer(api_client, rid, "has_symptoms", {"option": "yes"}).status_code == 200
    assert api_client.post(url, {"email": "one@example.org"}, format="json").status_code == 204
    # Hiding the question must not throw the marker away with the other answers.
    r = put_answer(api_client, rid, "has_symptoms", {"option": "no"})
    assert r.status_code == 200
    assert "contact_email" not in r.json()["visible"]
    assert "contact_email" not in r.json()["invalidated"]
    assert SurveyAnswer.objects.get(response_id=rid, question_key="contact_email").value == {
        "provided": True
    }
    assert api_client.post(url, {"email": "x@example.org"}, format="json").status_code == 400
    # Re-shown: the marker is back and a second address is not stored.
    r = put_answer(api_client, rid, "has_symptoms", {"option": "yes"})
    assert r.json()["invalidated"] == []
    assert api_client.get(f"/api/run/responses/{rid}/").json()["answers"]["contact_email"] == {
        "provided": True
    }
    assert api_client.post(url, {"email": "two@example.org"}, format="json").status_code == 204
    assert list(SurveyContact.objects.values_list("email", flat=True)) == ["one@example.org"]
    assert SurveyResponse.objects.get(pk=rid).last_question_key == "has_symptoms"
    put_answer(api_client, rid, "contact_email", {"provided": False})
    assert SurveyResponse.objects.get(pk=rid).last_question_key == "contact_email"
