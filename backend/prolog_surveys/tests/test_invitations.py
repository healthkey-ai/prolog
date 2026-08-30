"""Phase 7: invitations, repeat administration (both profiles)."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core import mail
from django.core.management import call_command

from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.invitations import (
    add_months,
    current_due_date,
    due_dates,
    schedule_due,
    send_pending,
)
from prolog_surveys.models import SurveyAdministration, SurveyInvitation, SurveyResponse
from prolog_surveys.tests.conftest import example_definition


def definition(**participation):
    doc = example_definition()
    doc["participation"] = {"anonymous": False, **participation}
    return doc


def test_due_dates_weeks_and_months():
    weekly = {"every": 2, "unit": "weeks", "start_date": "2026-01-01", "end_date": "2026-02-15"}
    assert list(due_dates(weekly, dt.date(2026, 3, 1))) == [
        dt.date(2026, 1, 1),
        dt.date(2026, 1, 15),
        dt.date(2026, 1, 29),
        dt.date(2026, 2, 12),
    ]
    monthly = {"every": 1, "unit": "months", "start_date": "2026-01-31"}
    assert list(due_dates(monthly, dt.date(2026, 4, 1))) == [
        dt.date(2026, 1, 31),
        dt.date(2026, 2, 28),
        dt.date(2026, 3, 31),
    ]
    assert add_months(dt.date(2024, 1, 31), 1) == dt.date(2024, 2, 29)
    assert list(due_dates(monthly, dt.date(2025, 12, 31))) == []


def test_current_due_date_is_the_open_cycle():
    monthly = {"every": 1, "unit": "months", "start_date": "2026-01-01"}
    assert current_due_date(monthly, dt.date(2025, 12, 31)) is None
    assert current_due_date(monthly, dt.date(2026, 1, 1)) == dt.date(2026, 1, 1)
    assert current_due_date(monthly, dt.date(2026, 3, 15)) == dt.date(2026, 3, 1)
    ended = {**monthly, "end_date": "2026-02-15"}
    assert current_due_date(ended, dt.date(2026, 2, 20)) == dt.date(2026, 2, 1)
    assert current_due_date(ended, dt.date(2026, 3, 1)) is None  # the schedule is over


@pytest.mark.django_db
def test_schedule_creates_only_the_current_cycle(settings):
    doc = definition(repeat={"every": 1, "unit": "months", "start_date": "2026-01-01"})
    version = load_definition(doc, activate=True).version
    inv = SurveyInvitation.objects.create(
        survey=version.survey, email="p@example.org", language="es"
    )
    # An invitation added mid-schedule gets this cycle's link, never a backlog.
    created = schedule_due(dt.date(2026, 3, 15))
    assert [a.due_at for a in created] == [dt.date(2026, 3, 1)]
    assert all(a.survey_version == version for a in created)
    assert schedule_due(dt.date(2026, 3, 15)) == []
    assert [a.due_at for a in schedule_due(dt.date(2026, 4, 2))] == [dt.date(2026, 4, 1)]
    # A scheduler that was down for two cycles does not back-fill them either.
    assert [a.due_at for a in schedule_due(dt.date(2026, 7, 10))] == [dt.date(2026, 7, 1)]
    assert inv.administrations.count() == 3
    assert send_pending() == 3


@pytest.mark.django_db
def test_one_off_survey_administered_once():
    version = load_definition(definition(), activate=True).version
    SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    assert len(schedule_due(dt.date(2026, 1, 1))) == 1
    assert schedule_due(dt.date(2026, 2, 1)) == []


@pytest.mark.django_db
def test_use_current_version_leaves_version_open():
    doc = definition(
        repeat={
            "every": 1,
            "unit": "weeks",
            "start_date": "2026-01-01",
            "use_current_version": True,
        }
    )
    version = load_definition(doc, activate=True).version
    SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    created = schedule_due(dt.date(2026, 1, 1))
    assert created[0].survey_version is None


@pytest.mark.django_db
def test_send_pending_emails_link(settings):
    settings.PROLOG_PUBLIC_URL = "https://survey.example.org"
    doc = definition()
    doc["title"]["fr"] = "Bilan de bien-être & vous"  # plain text: no HTML escaping
    version = load_definition(doc, activate=True).version
    inv = SurveyInvitation.objects.create(
        survey=version.survey, email="p@example.org", language="fr"
    )
    SurveyInvitation.objects.create(survey=version.survey, email="")  # no address: skipped
    schedule_due(dt.date(2026, 1, 1))
    assert send_pending() == 1
    assert send_pending() == 0
    message = mail.outbox[0]
    assert message.subject == "Bilan de bien-être & vous"
    assert "Bilan de bien-être & vous" in message.body
    assert "&amp; vous" in message.alternatives[0][0]
    admin_id = inv.administrations.get().id
    assert f"https://survey.example.org/s/sample-wellbeing?invite={admin_id}" in message.body
    assert message.alternatives[0][1] == "text/html"


@pytest.mark.django_db
def test_command(capsys):
    version = load_definition(definition(), activate=True).version
    SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    call_command("send_due_invitations")
    assert "created 1 administration(s), sent 1 invitation(s)" in capsys.readouterr().out


@pytest.mark.django_db
def test_invited_participant_flow(api_client):
    version = load_definition(definition(), activate=True).version
    inv = SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    admin = schedule_due(dt.date(2026, 1, 1))[0]
    # account survey without invitation or login is refused
    assert api_client.get("/api/run/surveys/sample-wellbeing/").status_code == 403
    assert (
        api_client.get(f"/api/run/surveys/sample-wellbeing/?invite={admin.id}").status_code == 200
    )
    r = api_client.post(
        "/api/run/responses/",
        {"slug": "sample-wellbeing", "language": "en", "invitation": str(admin.id)},
        format="json",
    )
    assert r.status_code == 201
    rid = r.json()["id"]
    assert SurveyResponse.objects.get(pk=rid).administration == admin
    # the same link resumes the same response
    r = api_client.post(
        "/api/run/responses/",
        {"slug": "sample-wellbeing", "language": "en", "invitation": str(admin.id)},
        format="json",
    )
    assert r.status_code == 200 and r.json()["id"] == rid
    assert api_client.get(f"/api/run/responses/{rid}/").status_code == 200
    # bad tokens
    assert (
        api_client.post(
            "/api/run/responses/",
            {"slug": "sample-wellbeing", "language": "en", "invitation": str(inv.id)},
            format="json",
        ).status_code
        == 403
    )
    assert api_client.get("/api/run/surveys/sample-wellbeing/?invite=nope").status_code == 403


@pytest.mark.django_db
def test_administration_uses_scheduled_version(api_client):
    doc = definition(repeat={"every": 1, "unit": "weeks", "start_date": "2026-01-01"})
    v1 = load_definition(doc, activate=True).version
    SurveyInvitation.objects.create(survey=v1.survey, email="p@example.org")
    admin = schedule_due(dt.date(2026, 1, 1))[0]
    doc["version"] = "1.1"
    v2 = load_definition(doc, activate=True).version
    assert SurveyAdministration.objects.get(pk=admin.pk).survey_version == v1  # archived now
    r = api_client.post(
        "/api/run/responses/",
        {"slug": "sample-wellbeing", "language": "en", "invitation": str(admin.id)},
        format="json",
    )
    assert r.status_code == 201
    # archived scheduled version falls back to the active one
    assert r.json()["version"] == v2.version


@pytest.mark.django_db
def test_anonymous_survey_takes_no_invitations(api_client, caplog):
    version = load_definition(definition(anonymous=True), activate=True).version
    SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    # Nothing is scheduled (so nothing is emailed) for an anonymous survey...
    assert schedule_due(dt.date(2026, 1, 1)) == []
    assert "anonymous" in caplog.text
    # ...and an administration created before the survey went anonymous is
    # not sent either (the link would be refused below).
    SurveyAdministration.objects.create(
        invitation=version.survey.invitations.get(), survey_version=None, due_at="2025-12-01"
    )
    assert send_pending() == 0 and not mail.outbox
    assert "not sent" in caplog.text
    SurveyAdministration.objects.all().delete()
    # ...and a token, however obtained, is refused rather than linked to the answers.
    admin = SurveyAdministration.objects.create(
        invitation=version.survey.invitations.get(), survey_version=version, due_at="2026-01-01"
    )
    r = api_client.post(
        "/api/run/responses/",
        {"slug": "sample-wellbeing", "language": "en", "invitation": str(admin.id)},
        format="json",
    )
    assert r.status_code == 400 and "invitation" in r.json()
    assert not SurveyResponse.objects.exists()
