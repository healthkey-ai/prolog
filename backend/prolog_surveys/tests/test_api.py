"""Phase 2: runner API."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model

from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.models import (
    SurveyAdministration,
    SurveyAnswer,
    SurveyConsent,
    SurveyContact,
    SurveyInvitation,
    SurveyResponse,
)


@pytest.fixture
def definition(example) -> dict:
    return example


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
    # Strong and weak validators both match (a proxy may weaken the ETag).
    for validator in (etag, f"W/{etag}", f'"other", {etag}'):
        r = api_client.get(
            "/api/run/surveys/sample-wellbeing/?lang=es", HTTP_IF_NONE_MATCH=validator
        )
        assert r.status_code == 304 and r.headers["ETag"] == etag, validator
    assert (
        api_client.get(
            "/api/run/surveys/sample-wellbeing/?lang=es", HTTP_IF_NONE_MATCH='"stale"'
        ).status_code
        == 200
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
    # Outside the window the survey is "closed" (410), not "not found" (404),
    # so the runner can say so; the same signal writes get later on.
    r = api_client.get("/api/run/surveys/sample-wellbeing/")
    assert r.status_code == 410 and r.json()["detail"] == "survey has closed"
    r = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    assert r.status_code == 410
    survey.effective_to = None
    survey.effective_from = "2999-01-01"
    survey.save()
    r = api_client.get("/api/run/surveys/sample-wellbeing/")
    assert r.status_code == 410 and r.json()["detail"] == "survey is not yet open"


def test_rejected_answer_carries_structured_issues(api_client, response_id):
    r = put_answer(api_client, response_id, "overall", {"value": 9})
    assert r.status_code == 400
    assert r.json() == {
        "value": [
            {
                "code": "value_out_of_range",
                "params": {"min": 1, "max": 5},
                "message": "value must be between 1 and 5",
            }
        ]
    }
    # Not-yet-visible questions are refused with a code too.
    r = put_answer(api_client, response_id, "symptoms", {"options": ["pain"]})
    assert r.status_code == 400 and r.json()["value"][0]["code"] == "not_visible"


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
    # A PATCH changes neither answers nor visibility, so the summary alone comes
    # back (the runner merges only the fields it patched).
    assert "answers" not in r.json() and "visible" not in r.json()
    assert (
        api_client.patch(
            f"/api/run/responses/{response_id}/", {"language": "de"}, format="json"
        ).status_code
        == 400
    )


def test_deactivated_invitation_revokes_its_response_links(api_client, db, definition):
    """The administration id in an invitation link is the credential for the
    response it started, so deactivating the invitation must close that
    response to the link's holder too (not only refuse new starts)."""
    definition["participation"] = {"anonymous": False}
    version = load_definition(definition, activate=True).version
    invitation = SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    administration = SurveyAdministration.objects.create(
        invitation=invitation, survey_version=version, due_at="2026-01-01"
    )
    r = api_client.post(
        "/api/run/responses/",
        {"slug": "sample-wellbeing", "language": "en", "invitation": str(administration.id)},
        format="json",
    )
    assert r.status_code == 201, r.content
    rid = r.json()["id"]
    assert put_answer(api_client, rid, "country", {"option": "GB"}).status_code == 200
    invitation.active = False
    invitation.save()
    calls = [
        lambda: api_client.get(f"/api/run/responses/{rid}/"),
        lambda: api_client.patch(
            f"/api/run/responses/{rid}/", {"last_question_key": "country"}, format="json"
        ),
        lambda: put_answer(api_client, rid, "age_band", {"option": "30_49"}),
        lambda: api_client.post(f"/api/run/responses/{rid}/submit/"),
        lambda: api_client.get(f"/api/run/surveys/sample-wellbeing/?response={rid}"),
        lambda: api_client.post(
            "/api/run/responses/",
            {"slug": "sample-wellbeing", "language": "en", "invitation": str(administration.id)},
            format="json",
        ),
    ]
    for call in calls:
        r = call()
        assert r.status_code == 403 and r.json()["detail"] == "invitation is no longer active"
    assert SurveyAnswer.objects.filter(response_id=rid).count() == 1  # nothing was written


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


def test_text_answer_cap_enforced_at_the_api(api_client, active, response_id):
    """Verification of the P1 fix: an oversized text is refused end to end (code + params)."""
    from prolog_surveys.engine.answers import MAX_TEXT_LENGTH

    # anything_else has max_length 5000, which is below the cap, so it applies as before
    r = put_answer(api_client, response_id, "anything_else", {"text": "a" * 5001})
    assert r.status_code == 400 and r.json()["value"][0] == {
        "code": "text_too_long",
        "params": {"max": 5000},
        "message": "text exceeds 5000 characters",
    }
    # a request body larger than the API's upload cap is refused outright
    r = api_client.put(
        f"/api/run/responses/{response_id}/answers/anything_else/",
        {"value": {"text": "a" * (MAX_TEXT_LENGTH * 30)}},
        format="json",
    )
    assert r.status_code == 400


def test_options_source_language_is_validated(api_client, active):
    # Only a language tag reaches gettext and the per-language cache; the
    # resolved (normalised) tag is echoed back.
    r = api_client.get("/api/run/options/iso3166_countries/?lang=pt-BR")
    assert r.status_code == 200 and r.json()["language"] == "pt-BR"
    r = api_client.get("/api/run/options/iso3166_countries/?lang=FR")
    assert r.status_code == 200 and r.json()["language"] == "fr"
    for bad in ("../../etc", "en; drop", "x" * 50, ""):
        r = api_client.get(f"/api/run/options/iso3166_countries/?lang={bad}")
        assert r.status_code == 400, bad
        assert "lang" in r.json()


def test_patch_rejects_unknown_last_question_key(api_client, response_id):
    r = api_client.patch(
        f"/api/run/responses/{response_id}/", {"last_question_key": "nope"}, format="json"
    )
    assert r.status_code == 400 and "last_question_key" in r.json()
    assert SurveyResponse.objects.get(pk=response_id).last_question_key == ""


def test_options_source_regional_language_is_localised(api_client, active):
    # gettext knows POSIX locale names; a BCP 47 region tag must reach it as
    # ``pt_BR`` (which also falls back to ``pt``), not be silently English.
    r = api_client.get("/api/run/options/iso3166_countries/?lang=pt-BR")
    assert r.json()["language"] == "pt-BR"
    assert any(o["key"] == "DE" and o["label"] == "Alemanha" for o in r.json()["options"])
    r = api_client.get("/api/run/options/iso3166_countries/?lang=es-MX")
    assert any(o["key"] == "DE" and o["label"] == "Alemania" for o in r.json()["options"])


# --- throttling --------------------------------------------------------------------


def test_answer_throttle_key_is_hashed(api_client, response_id):
    """The response id is the capability token (RUN-1); it never lands in the
    shared cache as a throttle key (CON-6)."""
    from django.core.cache import cache

    from prolog_surveys import conf

    assert put_answer(api_client, response_id, "country", {"option": "GB"}).status_code == 200
    keys = [k for k in cache._cache if "throttle_" in k]
    assert keys
    assert not any(str(response_id) in k for k in keys)
    assert any(conf.salted_hash(str(response_id)) in k for k in keys)


@pytest.mark.parametrize("method", ["put", "post"])
def test_answer_and_submit_are_bounded_per_client(api_client, active, monkeypatch, method):
    """A stream of writes to fresh random ids must hit a per-client limit, not
    only the per-response bucket (which is new for every id)."""
    import uuid

    from rest_framework.throttling import SimpleRateThrottle

    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "run.write", "2/hour")
    codes = []
    for _ in range(3):
        rid = uuid.uuid4()
        if method == "put":
            r = put_answer(api_client, rid, "country", {"option": "GB"})
        else:
            r = api_client.post(f"/api/run/responses/{rid}/submit/")
        codes.append(r.status_code)
    assert codes == [404, 404, 429]


def test_invitation_lock_covers_only_the_administration_row(api_client, db, definition):
    """FOR UPDATE without OF would also lock the joined invitation and survey
    rows for the whole start transaction."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    definition["participation"] = {"anonymous": False}
    version = load_definition(definition, activate=True).version
    invitation = SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    administration = SurveyAdministration.objects.create(
        invitation=invitation, survey_version=version, due_at="2026-01-01"
    )
    with CaptureQueriesContext(connection) as ctx:
        r = api_client.post(
            "/api/run/responses/",
            {"slug": "sample-wellbeing", "language": "en", "invitation": str(administration.id)},
            format="json",
        )
    assert r.status_code == 201, r.content
    locks = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
    assert any(f'FOR UPDATE OF "{SurveyAdministration._meta.db_table}"' in sql for sql in locks), (
        locks
    )


# --- contact capture failure -----------------------------------------------------------


def test_contact_storage_failure_never_reports_the_address(
    api_client, response_id, monkeypatch, caplog
):
    """A failure while storing the address is a 500 with the class name logged,
    never an unhandled exception whose report would carry the body (CON-3)."""

    def boom(**kwargs):
        raise RuntimeError("disk full while storing " + kwargs["email"])

    monkeypatch.setattr(SurveyContact.objects, "create", boom)
    r = api_client.post(
        f"/api/run/responses/{response_id}/contact/",
        {"email": "someone@example.org"},
        format="json",
    )
    assert r.status_code == 500
    assert "someone" not in r.content.decode()
    assert "RuntimeError" in caplog.text and "someone" not in caplog.text
    assert not SurveyAnswer.objects.filter(response_id=response_id).exists()


# --- admin -----------------------------------------------------------------------------


def test_admin_keeps_loader_owned_survey_fields_readonly(active, rf):
    """The loader identifies a survey by slug and rewrites title/theme_code on
    every load; editing them in the admin would be reverted (or orphan the
    survey), so only the effective window is editable once a survey exists."""
    from django.contrib.admin.sites import site

    from prolog_surveys.admin import SurveyAdmin
    from prolog_surveys.models import Survey

    request = rf.get("/admin/")
    readonly = set(SurveyAdmin(Survey, site).get_readonly_fields(request, active.survey))
    assert {"slug", "title", "theme_code", "allow_anonymous_participation"} <= readonly
    assert not {"effective_from", "effective_to"} & readonly
