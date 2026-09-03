"""Operational commands: startup loader resilience, retention guard rails."""

from __future__ import annotations

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from prolog_surveys.models import LifecycleStatus, Survey, SurveyResponse, SurveyVersion


@pytest.mark.django_db
def test_load_definitions_skips_unreadable_files_and_loads_the_rest(
    tmp_path, example, settings, capsys
):
    # A truncated file, a conflict-marked one and a non-UTF-8 one sit beside a
    # good definition: the good one loads, each bad one is reported, and the
    # command still fails so the operator notices.
    (tmp_path / "a-good.json").write_text(json.dumps(example))
    (tmp_path / "b-truncated.json").write_text(json.dumps(example)[:200])
    (tmp_path / "c-conflict.json").write_text("<<<<<<< HEAD\n" + json.dumps(example))
    (tmp_path / "d-latin1.json").write_bytes(b'{"title": "caf\xe9"}')
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    with pytest.raises(CommandError, match="3 of 4"):
        call_command("load_definitions")
    captured = capsys.readouterr()
    assert "created: sample-wellbeing@" in captured.out
    for name in ("b-truncated.json", "c-conflict.json", "d-latin1.json"):
        assert f"skipped unreadable definition: {tmp_path / name}" in captured.err
    assert SurveyVersion.objects.filter(survey__slug="sample-wellbeing").exists()


@pytest.mark.django_db
def test_load_definitions_exits_non_zero_on_invalid_definition(tmp_path, example, settings):
    example["sections"] = []
    (tmp_path / "invalid.json").write_text(json.dumps(example))
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    with pytest.raises(CommandError, match="1 of 1"):
        call_command("load_definitions")
    assert not SurveyVersion.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("days", [0, -1])
def test_purge_refuses_zero_or_negative_days(days, version_fixture, api_client):
    api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    with pytest.raises(CommandError, match="--days"):
        call_command("purge_abandoned_responses", "--days", str(days))
    with pytest.raises(CommandError, match="--days"):
        call_command("purge_abandoned_responses", "--days", str(days), "--dry-run")
    assert SurveyResponse.objects.count() == 1


@pytest.mark.django_db
def test_purge_refuses_zero_retention_setting(settings, version_fixture, api_client):
    api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    settings.PROLOG_ABANDONED_RESPONSE_DAYS = 0
    with pytest.raises(CommandError, match="PROLOG_ABANDONED_RESPONSE_DAYS"):
        call_command("purge_abandoned_responses")
    assert SurveyResponse.objects.count() == 1


@pytest.fixture
def version_fixture(db, example):
    from prolog_surveys.definitions.loader import load_definition

    return load_definition(example, activate=True).version


# --- admin: verify and load --------------------------------------------------


@pytest.fixture
def admin_login(db, client, django_user_model, settings):
    # Admin templates reference hashed static files, and nothing runs
    # collectstatic in tests: the manifest backend would raise on base.css
    # before a single assertion about the page.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    user = django_user_model.objects.create_superuser(username="root", password="pw")
    client.force_login(user)
    return client


def test_admin_shows_what_the_deployment_mounts(admin_login, tmp_path, settings, example):
    (tmp_path / "one.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    body = admin_login.get("/admin/prolog_surveys/survey/verify/").content.decode()

    assert "one.json" in body
    # and says what it is verifying against, because "valid" means little without it
    assert str(settings.PROLOG_SCHEMA_DIR) in body or "schema" in body


def test_admin_verify_writes_nothing(admin_login, tmp_path, settings, example):
    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json")},
    ).content.decode()

    assert "Valid" in body
    assert Survey.objects.count() == 0, "verify must not write"


def test_admin_verify_reports_every_error_in_the_page(admin_login, tmp_path, settings, example):
    """The validator's own output, not a summary: an administrator fixing a
    definition needs the code and the path."""
    example["sections"][0]["questions"][0]["config"] = {"options_source_include": ["DE"]}
    (tmp_path / "bad.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "bad.json")},
    ).content.decode()

    assert "Refused" in body
    assert "options_source_include" in body
    assert Survey.objects.count() == 0


def test_admin_loads_as_a_draft_never_active(admin_login, tmp_path, settings, example):
    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json"), "action": "load"},
        follow=True,
    )

    version = SurveyVersion.objects.get()
    assert version.status == LifecycleStatus.DRAFT
    assert version.source.endswith("s.json")


def test_admin_refuses_to_load_a_definition_with_errors(admin_login, tmp_path, settings, example):
    example["sections"][0]["questions"][0]["config"] = {"options_source_include": ["DE"]}
    (tmp_path / "bad.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "bad.json"), "action": "load"},
    )

    assert Survey.objects.count() == 0


def test_admin_verify_needs_a_staff_session(client, db):
    response = client.get("/admin/prolog_surveys/survey/verify/")

    assert response.status_code == 302 and "/login" in response["Location"]


def test_questions_and_responses_are_not_administered(admin_login):
    """They come from the definition and from the API; a second, unvalidated
    view of either is what this admin is not for."""
    assert admin_login.get("/admin/prolog_surveys/surveyquestion/").status_code == 404
    assert admin_login.get("/admin/prolog_surveys/surveyresponse/").status_code == 404
