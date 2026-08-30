"""Phase 6: exports, retention purge, health."""

from __future__ import annotations

import csv
import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.exports import write_contacts, write_responses
from prolog_surveys.models import SurveyContact, SurveyResponse


@pytest.fixture
def version(db, example):
    return load_definition(example, activate=True).version


def fill(api_client, rid, answers):
    for key, value in answers.items():
        r = api_client.put(
            f"/api/run/responses/{rid}/answers/{key}/", {"value": value}, format="json"
        )
        assert r.status_code == 200, (key, r.content)


@pytest.fixture
def submitted(api_client, version):
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "es"}, format="json"
    ).json()["id"]
    fill(
        api_client,
        rid,
        {
            "country": {"option": "GB"},
            "age_band": {"option": "30_49"},
            "birth_year": {"number": 1990},
            "last_visit": {"skipped": True},
            "overall": {"value": 4},
            "has_symptoms": {"option": "yes"},
            "symptoms": {"options": ["fatigue", "other"], "other_text": "Dizziness"},
            "symptom_impact": {"ratings": {"fatigue": 2, "other": 4}},
            "daily_activities": {"ratings": {"walking": 1, "housework": 2, "socialising": 3}},
            "outcome_ranking": {
                "order": ["independence", "energy", "side_effects", "fewer_visits"]
            },
            "support_wanted": {"options": ["peer"]},
            "told_clinician": {"option": "no"},
            "anything_else": {"text": "Thanks, all good"},
        },
    )
    assert (
        api_client.post(
            f"/api/run/responses/{rid}/contact/", {"email": "someone@example.org"}, format="json"
        ).status_code
        == 204
    )
    assert api_client.post(f"/api/run/responses/{rid}/submit/").status_code == 200
    return rid


def test_export_responses_shape(version, submitted, api_client):
    # an in-progress response must not appear by default
    api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    out = io.StringIO()
    assert write_responses(version, out) == 1
    rows = list(csv.reader(io.StringIO(out.getvalue())))
    header, row = rows[0], rows[1]
    record = dict(zip(header, row, strict=True))
    assert record["response_id"] == submitted
    assert record["language"] == "es" and record["status"] == "submitted"
    assert record["country"] == "GB"
    assert record["birth_year"] == "1990" and record["last_visit"] == "SKIPPED"
    assert record["symptoms.fatigue"] == "1" and record["symptoms.pain"] == "0"
    assert record["symptoms.other_text"] == "Dizziness"
    assert record["symptom_impact.fatigue"] == "2" and record["symptom_impact.pain"] == ""
    assert record["daily_activities.socialising"] == "3"
    assert record["outcome_ranking.independence"] == "1" and record["outcome_ranking.energy"] == "2"
    assert record["outcome_ranking.other"] == ""
    assert record["told_clinician"] == "no"
    assert record["anything_else"] == "Thanks, all good"
    assert record["contact_email"] == "1"
    assert "welcome" not in header
    assert "someone@example.org" not in out.getvalue()
    # hidden question stays empty
    assert record["worry_detail"] == ""


def test_export_contacts_separate(version, submitted):
    out = io.StringIO()
    assert write_contacts(version, out) == 1
    text = out.getvalue()
    assert "someone@example.org" in text
    assert submitted not in text
    assert "response" not in text.splitlines()[0]


def test_export_commands(version, submitted, tmp_path, capsys):
    call_command("export_responses", "sample-wellbeing", "--out", str(tmp_path / "r.csv"))
    call_command("export_contacts", "sample-wellbeing", "--out", str(tmp_path / "c.csv"))
    assert (tmp_path / "r.csv").read_text().count("\n") == 2
    assert "someone@example.org" in (tmp_path / "c.csv").read_text()
    call_command("export_responses", "sample-wellbeing", "--include-in-progress")
    assert "response_id" in capsys.readouterr().out


def test_purge_abandoned(version, api_client, capsys):
    old = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    fresh = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    SurveyResponse.objects.filter(pk=old).update(updated_at=timezone.now() - timedelta(days=120))
    call_command("purge_abandoned_responses", "--dry-run")
    assert "would delete 1" in capsys.readouterr().out
    assert SurveyResponse.objects.count() == 2
    call_command("purge_abandoned_responses")
    assert set(SurveyResponse.objects.values_list("id", flat=True)) == {
        __import__("uuid").UUID(fresh)
    }


def test_health_reports_checks(api_client, version):
    body = api_client.get("/api/health/").json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["active_surveys"] == 1
    assert "default" in body["checks"]["themes"]
    assert SurveyContact.objects.count() == 0
