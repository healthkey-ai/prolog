"""Phase 7: invitations, repeat administration (both profiles)."""

from __future__ import annotations

import datetime as dt
import logging

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from prolog_surveys import invitations
from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.invitations import (
    add_months,
    current_due_date,
    due_dates,
    schedule_due,
    send_pending,
)
from prolog_surveys.models import (
    SurveyAdministration,
    SurveyInvitation,
    SurveyResponse,
    SurveyVersion,
)
from prolog_surveys.tests.conftest import example_definition


def definition(**participation):
    doc = example_definition()
    doc["participation"] = {"anonymous": False, **participation}
    return doc


@pytest.fixture(autouse=True)
def public_url(settings):
    """The test runner turns DEBUG off, where the localhost default is refused
    (see test_local_public_url_refuses_to_send_outside_debug)."""
    settings.PROLOG_PUBLIC_URL = "https://survey.example.org"


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


@pytest.mark.django_db
@pytest.mark.parametrize("field, days", [("effective_to", -1), ("effective_from", 1)])
def test_closed_survey_is_neither_scheduled_nor_sent(field, days, caplog):
    caplog.set_level(logging.INFO, logger="prolog_surveys.invitations")
    doc = definition(repeat={"every": 1, "unit": "weeks", "start_date": "2026-01-01"})
    version = load_definition(doc, activate=True).version
    survey = version.survey
    setattr(survey, field, timezone.localdate() + dt.timedelta(days=days))
    survey.save()
    invitation = SurveyInvitation.objects.create(survey=survey, email="p@example.org")
    # Outside the effective window the link would be refused (410): no administration...
    assert schedule_due() == []
    assert not SurveyAdministration.objects.exists()
    assert "sample-wellbeing is not scheduled" in caplog.text
    # ...and one created before the window closed stays unsent (not marked sent)...
    admin = SurveyAdministration.objects.create(
        invitation=invitation, survey_version=version, due_at=dt.date(2026, 1, 1)
    )
    assert send_pending() == 0 and not mail.outbox
    admin.refresh_from_db()
    assert admin.sent_at is None
    assert "not sent" in caplog.text
    # ...until the survey is open again.
    setattr(survey, field, None)
    survey.save()
    assert send_pending() == 1


@pytest.mark.django_db
def test_one_broken_schedule_does_not_stop_the_others(caplog):
    good = load_definition(definition(), activate=True).version
    bad_doc = definition(repeat={"every": 1, "unit": "weeks", "start_date": "2026-01-01"})
    bad_doc["slug"] = "broken"
    bad = load_definition(bad_doc, activate=True).version
    # The validator refuses this, so corrupt the stored definition directly.
    bad.definition["participation"]["repeat"]["start_date"] = "2026-13-01"
    SurveyVersion.objects.filter(pk=bad.pk).update(definition=bad.definition)
    for version in (good, bad):
        SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    created = schedule_due(dt.date(2026, 1, 1))
    assert [a.invitation.survey.slug for a in created] == ["sample-wellbeing"]
    assert "could not schedule survey broken" in caplog.text


@pytest.mark.django_db
def test_one_failed_email_does_not_stop_the_batch(monkeypatch, caplog):
    version = load_definition(definition(), activate=True).version
    for address in ("a@example.org", "b@example.org"):
        SurveyInvitation.objects.create(survey=version.survey, email=address)
    schedule_due(dt.date(2026, 1, 1))
    real_send = invitations._send_one

    def flaky(mailer, administration, version):
        if administration.invitation.email == "a@example.org":
            raise RuntimeError("mail server hiccup")
        return real_send(mailer, administration, version)

    monkeypatch.setattr(invitations, "_send_one", flaky)
    assert send_pending() == 1
    assert [m.to for m in mail.outbox] == [["b@example.org"]]
    failed = SurveyAdministration.objects.get(sent_at__isnull=True)
    assert f"could not send invitation {failed.invitation_id}" in caplog.text
    assert "RuntimeError" in caplog.text
    # The administration id is the participant's credential and the exception
    # text of a mail server may carry the address: neither belongs in a log.
    assert str(failed.pk) not in caplog.text
    assert "a@example.org" not in caplog.text
    assert "mail server hiccup" not in caplog.text


@pytest.mark.django_db
def test_unsent_message_is_not_marked_sent(monkeypatch, caplog):
    # A backend that reports 0 sent without raising must leave the
    # administration pending so the next run retries it.
    class _ZeroMailer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def send_messages(self, messages):
            return 0

    monkeypatch.setattr(invitations, "get_connection", lambda *a, **kw: _ZeroMailer())
    version = load_definition(definition(), activate=True).version
    SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    schedule_due(dt.date(2026, 1, 1))
    with caplog.at_level(logging.WARNING, logger="prolog_surveys.invitations"):
        assert send_pending() == 0
    assert SurveyAdministration.objects.get().sent_at is None
    assert "not sent" in caplog.text


@pytest.mark.django_db
def test_email_chrome_follows_the_invitation_language(settings):
    settings.PROLOG_PUBLIC_URL = "https://survey.example.org"
    version = load_definition(definition(), activate=True).version
    for lang in ("fr", "pt-BR", "xx"):
        SurveyInvitation.objects.create(
            survey=version.survey, email=f"{lang}@example.org", language=lang
        )
    schedule_due(dt.date(2026, 1, 1))
    assert send_pending() == 3
    by_recipient = {m.to[0]: m for m in mail.outbox}
    french = by_recipient["fr@example.org"]
    assert "You are invited" not in french.body
    assert invitations.EMAIL_STRINGS["fr"]["intro"] in french.body
    assert invitations.EMAIL_STRINGS["fr"]["open"] in french.alternatives[0][0]
    assert 'lang="fr"' in french.alternatives[0][0]
    # A regional variant falls back to its base language, an unknown one to English.
    assert invitations.EMAIL_STRINGS["pt"]["intro"] in by_recipient["pt-BR@example.org"].body
    assert invitations.EMAIL_STRINGS["en"]["intro"] in by_recipient["xx@example.org"].body


@pytest.mark.django_db
def test_concurrent_run_creating_the_same_cycle_does_not_abort_the_batch(monkeypatch):
    version = load_definition(definition(), activate=True).version
    first, second = (
        SurveyInvitation.objects.create(survey=version.survey, email=f"{n}@example.org")
        for n in ("a", "b")
    )
    real_bulk_create = SurveyAdministration.objects.bulk_create

    def racing_bulk_create(objs, **kwargs):
        # Another run inserted the first invitation's administration between
        # this run's read of the existing ones and its insert.
        SurveyAdministration.objects.create(
            invitation=first, survey_version=version, due_at=dt.date(2026, 1, 1)
        )
        return real_bulk_create(objs, **kwargs)

    monkeypatch.setattr(SurveyAdministration.objects, "bulk_create", racing_bulk_create)
    created = schedule_due(dt.date(2026, 1, 1))
    assert [a.invitation_id for a in created] == [second.id]
    assert SurveyAdministration.objects.count() == 2


@pytest.mark.django_db
def test_command_refuses_to_overlap_a_running_instance(capsys):
    from django.db import connections

    version = load_definition(definition(), activate=True).version
    SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    other = connections.create_connection("default")
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [invitations.RUN_LOCK_KEY])
            assert cursor.fetchone()[0] is True
        call_command("send_due_invitations")
        assert "already running" in capsys.readouterr().out
        assert not SurveyAdministration.objects.exists() and not mail.outbox
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [invitations.RUN_LOCK_KEY])
    finally:
        other.close()
    call_command("send_due_invitations")
    assert "created 1 administration(s), sent 1 invitation(s)" in capsys.readouterr().out
    # The lock is released at the end of the run.
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [invitations.RUN_LOCK_KEY])
        assert cursor.fetchone()[0] is True
        cursor.execute("SELECT pg_advisory_unlock(%s)", [invitations.RUN_LOCK_KEY])


@pytest.mark.django_db
def test_administration_without_a_version_is_reported(caplog):
    caplog.set_level(logging.INFO, logger="prolog_surveys.invitations")
    doc = definition(repeat={"every": 1, "unit": "weeks", "start_date": "2026-01-01"})
    v1 = load_definition(doc, activate=True).version
    SurveyInvitation.objects.create(survey=v1.survey, email="p@example.org")
    schedule_due(dt.date(2026, 1, 1))
    # The scheduled version is archived and nothing is active any more.
    SurveyVersion.objects.filter(pk=v1.pk).update(status="archived")
    assert send_pending() == 0 and not mail.outbox
    assert "invitation for survey sample-wellbeing not sent (no active version)" in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url", ["http://localhost:5173", "http://127.0.0.1:8000", "https://[::1]/", "", "/s"]
)
def test_local_public_url_refuses_to_send_outside_debug(settings, caplog, url):
    settings.DEBUG = False
    settings.PROLOG_PUBLIC_URL = url
    version = load_definition(definition(), activate=True).version
    SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    schedule_due(dt.date(2026, 1, 1))
    assert send_pending() == 0 and not mail.outbox
    assert "PROLOG_PUBLIC_URL" in caplog.text
    # Nothing is stamped: the batch goes out once the URL is corrected.
    assert SurveyAdministration.objects.get().sent_at is None
    settings.PROLOG_PUBLIC_URL = "https://survey.example.org"
    assert send_pending() == 1


@pytest.mark.django_db
def test_local_public_url_is_fine_under_debug(settings):
    settings.DEBUG = True
    settings.PROLOG_PUBLIC_URL = "http://localhost:5173"
    version = load_definition(definition(), activate=True).version
    SurveyInvitation.objects.create(survey=version.survey, email="p@example.org")
    schedule_due(dt.date(2026, 1, 1))
    assert send_pending() == 1
    assert "http://localhost:5173/s/sample-wellbeing?invite=" in mail.outbox[0].body


@pytest.mark.parametrize(("lang", "noun"), [("es", "encuesta"), ("pt", "pesquisa")])
def test_email_open_link_uses_the_runner_noun(lang, noun):
    # frontend/src/i18n/<lang>.json heads the page Encuesta / Pesquisa.
    assert noun in invitations.EMAIL_STRINGS[lang]["open"].lower()
