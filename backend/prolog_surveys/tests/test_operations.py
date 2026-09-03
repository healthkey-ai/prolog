"""Operational commands: startup loader resilience, retention guard rails."""

from __future__ import annotations

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from prolog_surveys.definitions.loader import discover
from prolog_surveys.models import LifecycleStatus, Survey, SurveyResponse, SurveyVersion
from prolog_surveys.themes import validate_theme
from prolog_surveys.themes.registry import discover_themes


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


# --- one folder per survey ---------------------------------------------------


def _bundle(root, name, example, version="1.0"):
    """A survey the way a deployment with several of them keeps one: its
    definition, its theme and the theme's assets in a folder of its own."""
    import copy

    folder = root / name
    (folder / "theme").mkdir(parents=True)
    doc = copy.deepcopy(example)
    doc["slug"] = name
    doc["version"] = version
    (folder / "survey.json").write_text(json.dumps(doc), encoding="utf-8")
    (folder / "theme" / "theme.json").write_text(
        json.dumps({"code": name, "name": name, "colors": {"light": {}}}), encoding="utf-8"
    )
    return folder


def test_definitions_are_found_in_a_folder_per_survey(tmp_path, settings, example):
    """Two surveys, two folders — not two files pooled in one directory."""
    _bundle(tmp_path, "alpha", example)
    _bundle(tmp_path, "beta", example)
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    found = [p.name for p in discover()]

    assert sorted(found) == ["survey.json", "survey.json"]
    assert len({p.parent.name for p in discover()}) == 2


def test_a_theme_beside_its_survey_is_not_taken_for_a_definition(tmp_path, settings, example):
    """theme.json is the one thing under a definition root that is not one."""
    _bundle(tmp_path, "alpha", example)
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    assert all(p.name != "theme.json" for p in discover())


def test_themes_are_found_at_any_depth(tmp_path, settings, example):
    _bundle(tmp_path, "alpha", example)
    settings.PROLOG_THEME_DIRS = [str(tmp_path)]

    found = discover_themes()

    assert [p.name for p in found] == ["theme"]


def test_a_theme_is_validated_from_its_file_or_its_folder(tmp_path, settings, example):
    folder = _bundle(tmp_path, "alpha", example) / "theme"

    from_folder, _ = validate_theme(folder)
    from_file, _ = validate_theme(folder / "theme.json")

    assert from_folder == from_file == {"code": "alpha", "name": "alpha", "colors": {"light": {}}}


def test_admin_refuses_a_path_outside_what_the_deployment_mounts(
    admin_login, tmp_path, settings, example
):
    """A staff form that reads any path is a file-disclosure hole."""
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path / "mounted")]
    settings.PROLOG_THEME_DIRS = []
    (tmp_path / "mounted").mkdir()
    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps(example), encoding="utf-8")

    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/", {"definition_path": str(outside)}
    ).content.decode()

    assert "outside every directory this deployment mounts" in body
    assert Survey.objects.count() == 0


def test_admin_refuses_a_path_that_walks_out_of_a_root(admin_login, tmp_path, settings, example):
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    settings.PROLOG_DEFINITION_DIRS = [str(mounted)]
    settings.PROLOG_THEME_DIRS = []
    (tmp_path / "secret.json").write_text(json.dumps(example), encoding="utf-8")

    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(mounted / ".." / "secret.json")},
    ).content.decode()

    assert "outside every directory this deployment mounts" in body


def test_admin_accepts_a_theme_beside_its_survey(admin_login, tmp_path, settings, example):
    folder = _bundle(tmp_path, "alpha", example)
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    settings.PROLOG_THEME_DIRS = []

    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {
            "definition_path": str(folder / "survey.json"),
            "theme_dir": str(folder / "theme" / "theme.json"),
        },
    ).content.decode()

    assert "outside every directory" not in body
    assert "Valid" in body or "Refused" in body


def test_the_survey_list_says_where_it_reads_from(admin_login, tmp_path, settings, example):
    """"No surveys" and "that directory is not there" look identical until
    something says which one it is."""
    mounted = tmp_path / "surveys"
    (mounted / "alpha").mkdir(parents=True)
    (mounted / "alpha" / "survey.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(mounted), str(tmp_path / "missing")]
    settings.PROLOG_THEME_DIRS = []

    body = admin_login.get("/admin/prolog_surveys/survey/").content.decode()

    assert "PROLOG_DEFINITION_DIRS" in body
    assert str(mounted) in body
    assert "directory does not exist" in body, "a misconfigured root must say so"
    assert "PROLOG_THEME_DIRS" in body and "nothing configured" in body


def test_adding_a_survey_takes_you_to_the_picker(admin_login):
    """A survey is loaded from a definition, not typed into a form: the fields
    a form would offer are the loader's and it rewrites them on every load."""
    response = admin_login.get("/admin/prolog_surveys/survey/add/")

    assert response.status_code == 302
    assert response["Location"].endswith("/admin/prolog_surveys/survey/verify/")


def test_the_picker_lists_what_is_mounted(admin_login, tmp_path, settings, example):
    folder = _bundle(tmp_path, "alpha", example)
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    settings.PROLOG_THEME_DIRS = [str(tmp_path)]

    body = admin_login.get("/admin/prolog_surveys/survey/verify/").content.decode()

    assert str(folder / "survey.json") in body
    assert str(folder / "theme") in body
