"""Operational commands: startup loader resilience, retention guard rails."""

from __future__ import annotations

import json
import re

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from prolog_surveys.definitions import loader
from prolog_surveys.definitions.loader import activate_version, discover, publish_version
from prolog_surveys.models import LifecycleStatus, Survey, SurveyResponse, SurveyVersion
from prolog_surveys.tests.conftest import make_response
from prolog_surveys.themes import registry as theme_registry
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
        follow=True,
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
        follow=True,
    ).content.decode()

    assert "has errors" in body and '<ul class="messagelist">' in body
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
        "/admin/prolog_surveys/survey/verify/", {"definition_path": str(outside)}, follow=True
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
        follow=True,
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
        follow=True,
    ).content.decode()

    assert "outside every directory" not in body
    assert "Valid" in body or "Refused" in body


def test_the_survey_list_says_where_it_reads_from(admin_login, tmp_path, settings, example):
    """ "No surveys" and "that directory is not there" look identical until
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


def test_load_actually_creates_the_survey(admin_login, tmp_path, settings, example):
    """The button submitted two fields named `action`, so the hidden empty one
    won and Load quietly re-verified instead of loading."""
    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    response = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json"), "action": "load"},
        follow=True,
    )

    assert Survey.objects.filter(slug=example["slug"]).exists()
    assert "Created" in response.content.decode()


def test_loading_the_same_definition_twice_says_it_already_exists(
    admin_login, tmp_path, settings, example
):
    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    post = lambda: admin_login.post(  # noqa: E731
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json"), "action": "load"},
        follow=True,
    )
    post()

    response = post()
    body = response.content.decode()

    assert response.status_code == 200, "nothing was written, so there is nowhere to go"
    assert "Nothing to load" in body and "Edit the file and re-load" in body
    assert 'class="warning"' in body, "not an error and not a success"
    assert SurveyVersion.objects.count() == 1, "a second row would be a second truth"


def test_changing_a_published_version_is_refused_on_the_page(
    admin_login, tmp_path, settings, example
):
    """A response records which version it answered, so the content of one
    cannot change under it."""
    import copy

    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json"), "action": "load"},
        follow=True,
    )
    version = SurveyVersion.objects.get()
    activate_version(version)
    publish_version(version)

    edited = copy.deepcopy(example)
    edited["title"]["en"] = "Something else"
    (tmp_path / "s.json").write_text(json.dumps(edited), encoding="utf-8")
    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json"), "action": "load"},
        follow=True,
    ).content.decode()

    assert "immutable" in body or "published" in body
    version.refresh_from_db()
    assert version.definition["title"]["en"] == example["title"]["en"]


# --- adding a version to a survey that exists --------------------------------


def _load(admin_login, path, **extra):
    return admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(path), "action": "load", **extra},
        follow=True,
    )


def test_the_survey_page_offers_another_version(admin_login, db, example):
    survey = loader.load_definition(example).version.survey

    body = admin_login.get(f"/admin/prolog_surveys/survey/{survey.pk}/change/").content.decode()

    assert "Add another version" in body
    assert f"verify/?survey={survey.slug}" in body


def test_adding_a_version_presets_the_survey_theme(admin_login, db, example, tmp_path, settings):
    """A new version usually keeps the theme; it stays editable because
    sometimes changing it is the point."""
    theme = tmp_path / "flf"
    theme.mkdir()
    (theme / "theme.json").write_text(
        json.dumps({"code": "flf", "name": "flf", "colors": {"light": {}}}), encoding="utf-8"
    )
    settings.PROLOG_THEME_DIRS = [str(tmp_path)]
    theme_registry.reload()
    example["theme"] = "flf"
    survey = loader.load_definition(example).version.survey

    body = admin_login.get(
        f"/admin/prolog_surveys/survey/verify/?survey={survey.slug}"
    ).content.decode()

    assert f"Add a version of {survey.slug}" in body
    assert f'value="{theme}"' in body


def test_a_definition_for_another_survey_is_refused(admin_login, db, example, tmp_path, settings):
    """It would create a second survey, which is not what the button said."""
    import copy

    survey = loader.load_definition(example).version.survey
    other = copy.deepcopy(example)
    other["slug"] = "something-else"
    (tmp_path / "other.json").write_text(json.dumps(other), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    body = _load(admin_login, tmp_path / "other.json", survey=survey.slug).content.decode()

    assert "would create a second survey" in body
    assert not Survey.objects.filter(slug="something-else").exists()


def test_a_bumped_version_lands_on_the_same_survey(admin_login, db, example, tmp_path, settings):
    import copy

    survey = loader.load_definition(example).version.survey
    nxt = copy.deepcopy(example)
    nxt["version"] = "9.9"
    (tmp_path / "next.json").write_text(json.dumps(nxt), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    _load(admin_login, tmp_path / "next.json", survey=survey.slug)

    assert Survey.objects.count() == 1
    assert sorted(v.version for v in survey.versions.all()) == [example["version"], "9.9"]
    assert survey.versions.get(version="9.9").status == LifecycleStatus.DRAFT


def test_the_versions_inline_offers_no_blank_row(admin_login, db, example):
    """Django's inline add link offered a version to type by hand — a row with
    no definition and nothing validated, which is the whole thing this admin
    is meant to prevent. The object-tools link is the way in."""
    survey = loader.load_definition(example).version.survey

    body = admin_login.get(f"/admin/prolog_surveys/survey/{survey.pk}/change/").content.decode()

    # The add link is drawn by Django's inline JS, not by the server, so the
    # thing to assert is what the JS reads: max_num 0 means it offers no row.
    assert 'name="versions-MAX_NUM_FORMS"' in body
    max_num = re.search(r'name="versions-MAX_NUM_FORMS"[^>]*value="(\d+)"', body).group(1)
    assert max_num == "0", "a blank version row could be typed by hand"
    assert "Add another version" in body, "the picker link stays"


def test_a_refused_version_says_so_in_the_error_slot(admin_login, db, example, tmp_path, settings):
    """Every refusal is said in the same place on the page it happened on:
    there is nothing to navigate to when nothing was written."""
    import copy

    version = loader.load_definition(example, activate=True).version
    survey = version.survey
    loader.publish_version(version)
    edited = copy.deepcopy(example)
    edited["title"]["en"] = "Something else"
    (tmp_path / "edited.json").write_text(json.dumps(edited), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    response = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {
            "definition_path": str(tmp_path / "edited.json"),
            "action": "load",
            "survey": survey.slug,
        },
        follow=True,
    )

    # An error stays where it can be corrected — and it is reached by a GET, so
    # Back is a page rather than "confirm form resubmission".
    assert response.redirect_chain[-1][0].startswith("/admin/prolog_surveys/survey/verify/")
    body = response.content.decode()
    assert '<ul class="messagelist">' in body and 'class="error"' in body


def test_a_mismatched_slug_is_said_in_the_error_slot(admin_login, db, example, tmp_path, settings):
    import copy

    survey = loader.load_definition(example).version.survey
    other = copy.deepcopy(example)
    other["slug"] = "something-else"
    (tmp_path / "other.json").write_text(json.dumps(other), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "other.json"), "action": "load", "survey": survey.slug},
        follow=True,
    ).content.decode()

    assert "would create a second survey" in body
    assert '<ul class="messagelist">' in body
    assert not Survey.objects.filter(slug="something-else").exists()


def test_a_successful_load_lands_on_the_survey_not_the_list(
    admin_login, db, example, tmp_path, settings
):
    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    response = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json"), "action": "load"},
    )

    survey = Survey.objects.get()
    assert response["Location"] == f"/admin/prolog_surveys/survey/{survey.pk}/change/"


def test_the_verify_page_renders_no_template_source(admin_login):
    """A multi-line {# #} is not a comment in Django, it is text on the page —
    which is how an explanation of the button markup ended up above the
    buttons."""
    body = admin_login.get("/admin/prolog_surveys/survey/verify/").content.decode()

    assert "{#" not in body and "#}" not in body
    assert "{%" not in body and "%}" not in body


def test_the_buttons_carry_the_admin_button_classes(admin_login, tmp_path, settings, example):
    """Django styles .button and .button.default; a bare <button> gets neither."""
    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json")},
        follow=True,
    ).content.decode()

    assert 'class="button default"' in body, "Verify is the primary action"
    assert 'value="load" class="button"' in body, "Load is styled, and offered once it verifies"


def test_the_buttons_are_sized_like_the_admin_save_row(admin_login):
    """Django's own sizing selector is .submit-row input, which never matches a
    <button>: without this the buttons render at the browser's default size
    beside an admin that is not."""
    body = admin_login.get("/admin/prolog_surveys/survey/verify/").content.decode()

    assert ".submit-row button" in body
    assert "padding: 10px 15px" in body


def test_every_outcome_uses_the_same_slot(admin_login, tmp_path, settings, example):
    """One place to look, whatever went wrong: a missing choice and a version
    that already exists were previously said in two different ways, one of
    them on a different page."""
    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    nothing_chosen = admin_login.post(
        "/admin/prolog_surveys/survey/verify/", {}, follow=True
    ).content.decode()
    admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json"), "action": "load"},
        follow=True,
    )
    already_there = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json"), "action": "load"},
        follow=True,
    ).content.decode()

    for body in (nothing_chosen, already_there):
        assert body.count('<ul class="messagelist">') == 1
    assert "Choose a mounted definition" in nothing_chosen
    assert "Nothing to load" in already_there


# --- test responses, and the act that ends them ------------------------------


def test_the_page_asks_before_discarding_test_responses(admin_login, tmp_path, settings, example):
    """A version being tried out has responses against it. They are test data
    until it is published — but the page says what it is about to delete and
    waits, because only the administrator knows that is what they are."""
    import copy

    from prolog_surveys.models import ResponseStatus, SurveyResponse

    version = loader.load_definition(example, activate=True).version
    make_response(version, language="en")
    make_response(version, language="en", status=ResponseStatus.SUBMITTED)
    edited = copy.deepcopy(example)
    edited["title"]["en"] = "Corrected title"
    (tmp_path / "s.json").write_text(json.dumps(edited), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    post = {"definition_path": str(tmp_path / "s.json")}

    asked = admin_login.post(
        "/admin/prolog_surveys/survey/verify/", {**post, "action": "load"}, follow=True
    ).content.decode()

    assert "2 response" in asked and "Discard 2 responses and load" in asked
    version.refresh_from_db()
    assert version.definition["title"]["en"] == example["title"]["en"], "nothing written yet"

    admin_login.post(
        "/admin/prolog_surveys/survey/verify/", {**post, "action": "load_discarding"}, follow=True
    )

    version.refresh_from_db()
    assert version.definition["title"]["en"] == "Corrected title"
    assert not SurveyResponse.objects.filter(survey_version=version).exists()


def test_publishing_freezes_the_version_from_the_page(admin_login, tmp_path, settings, example):
    import copy

    version = loader.load_definition(example, activate=True).version
    url = f"/admin/prolog_surveys/survey/publish/{version.pk}/"

    shown = admin_login.get(url).content.decode()
    assert "cannot be undone" in shown
    version.refresh_from_db()
    assert not version.is_published, "a GET says what it costs and writes nothing"

    admin_login.post(url, follow=True)

    version.refresh_from_db()
    assert version.is_published and not version.is_mutable

    edited = copy.deepcopy(example)
    edited["title"]["en"] = "Corrected title"
    (tmp_path / "s.json").write_text(json.dumps(edited), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    refused = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": str(tmp_path / "s.json"), "action": "load"},
        follow=True,
    ).content.decode()

    assert "bump the version" in refused
    assert "Discard" not in refused, "a published version offers no way to discard its responses"
    version.refresh_from_db()
    assert version.definition["title"]["en"] == example["title"]["en"]


def test_the_survey_page_offers_publishing_only_while_it_is_open(admin_login, db, example):
    version = loader.load_definition(example, activate=True).version
    page = f"/admin/prolog_surveys/survey/{version.survey_id}/change/"

    body = admin_login.get(page).content.decode()
    assert f"/admin/prolog_surveys/survey/publish/{version.pk}/" in body

    loader.publish_version(version)

    body = admin_login.get(page).content.decode()
    assert f"/admin/prolog_surveys/survey/publish/{version.pk}/" not in body
    assert "frozen" in body


# --- re-loading a version from the row it is on ------------------------------


def test_the_row_offers_re_load_and_the_page_arrives_verified(
    admin_login, tmp_path, settings, example
):
    """Re-load starts from the file the version came from: the administrator
    pressed a button on a row, not "find me a file"."""
    import copy

    path = tmp_path / "s.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    version = loader.load_file(path, activate=True).version
    survey_page = admin_login.get(
        f"/admin/prolog_surveys/survey/{version.survey_id}/change/"
    ).content.decode()

    link = (
        f"/admin/prolog_surveys/survey/verify/?survey={version.survey.slug}"
        f"&version={version.version}"
    )
    assert link.replace("&", "&amp;") in survey_page, "an href says &amp;, not a bare &"

    edited = copy.deepcopy(example)
    edited["title"]["en"] = "Corrected title"
    path.write_text(json.dumps(edited), encoding="utf-8")

    page = admin_login.get(link).content.decode()

    assert str(path) in page, "the file it came from is chosen"
    assert "No errors and no warnings" in page, "verified on arrival"
    assert f"Re-load {version.version}" in page

    admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {
            "definition_path": str(path),
            "survey": version.survey.slug,
            "version": version.version,
            "action": "load",
        },
        follow=True,
    )

    version.refresh_from_db()
    assert version.definition["title"]["en"] == "Corrected title"


def test_re_loading_a_file_that_bumped_its_version_says_so(
    admin_login, tmp_path, settings, example
):
    import copy

    path = tmp_path / "s.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    version = loader.load_file(path, activate=True).version
    bumped = copy.deepcopy(example)
    bumped["version"] = "9.9"
    path.write_text(json.dumps(bumped), encoding="utf-8")

    page = admin_login.get(
        f"/admin/prolog_surveys/survey/verify/?survey={version.survey.slug}"
        f"&version={version.version}"
    ).content.decode()

    assert "adds a version rather than replacing" in page


def test_a_published_version_offers_no_re_load(admin_login, db, example):
    version = loader.load_definition(example, activate=True).version
    loader.publish_version(version)

    page = admin_login.get(
        f"/admin/prolog_surveys/survey/{version.survey_id}/change/"
    ).content.decode()

    assert "Re-load" not in page and "Publish…" not in page


def test_every_control_in_a_submit_row_is_sized_the_same(admin_login, db, example):
    """A <button>, an <a class="button"> and Django's own input rule are three
    different sets of metrics; the pages that mix them say so once."""
    version = loader.load_definition(example).version

    page = admin_login.get(f"/admin/prolog_surveys/survey/publish/{version.pk}/").content.decode()

    # One rule for all three kinds of control, so Cancel is the height of the
    # button beside it rather than Django's third set of metrics.
    assert ".submit-row a.button" in page and ".submit-row button" in page
    assert 'class="button cancel-link"' in page


def test_no_outcome_leaves_the_browser_on_a_posted_page(admin_login, tmp_path, settings, example):
    """Back must be a page, not "confirm form resubmission".

    Every outcome of the form — verified, refused, nothing chosen, already
    loaded — is reached by a redirect to a GET, so the browser has an address
    to go back to and reloading repeats nothing. The one exception is an
    uploaded file, which a redirect cannot carry.
    """
    import copy

    bad = copy.deepcopy(example)
    bad["sections"][0]["questions"][0]["config"] = {"options_source_include": ["DE"]}
    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    good = str(tmp_path / "s.json")

    posts = [
        {},  # nothing chosen
        {"definition_path": good},  # verify
        {"definition_path": str(tmp_path / "bad.json"), "action": "load"},  # refused
        {"definition_path": good, "action": "load"},  # loads
        {"definition_path": good, "action": "load"},  # already there
    ]
    for post in posts:
        response = admin_login.post("/admin/prolog_surveys/survey/verify/", post)
        assert response.status_code == 302, f"{post} rendered a page a POST can be repeated on"

    # And the GET it lands on renders the same verdict, without asking twice.
    landing = admin_login.get(
        "/admin/prolog_surveys/survey/verify/", {"definition_path": good}
    ).content.decode()
    assert "Valid" in landing and landing.count('<ul class="messagelist">') <= 1


# --- who may do this ---------------------------------------------------------


@pytest.fixture
def staff_without_permissions(db, client, django_user_model, settings):
    """A staff session and nothing else — Django's own minimum for /admin/."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    user = django_user_model.objects.create_user(username="peon", password="pw", is_staff=True)
    client.force_login(user)
    return client


def test_a_staff_session_alone_cannot_load_or_discard(
    staff_without_permissions, tmp_path, settings, example
):
    """admin_view asks only for a staff session, which is not a permission to
    replace what an instrument says or to delete the responses given to it."""
    import copy

    version = loader.load_definition(example, activate=True).version
    make_response(version, language="en")
    edited = copy.deepcopy(example)
    edited["title"]["en"] = "Rewritten without permission"
    (tmp_path / "s.json").write_text(json.dumps(edited), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    for action in ("load", "load_discarding"):
        staff_without_permissions.post(
            "/admin/prolog_surveys/survey/verify/",
            {"definition_path": str(tmp_path / "s.json"), "action": action},
        )

    version.refresh_from_db()
    assert version.definition["title"]["en"] == example["title"]["en"]
    assert SurveyResponse.objects.filter(survey_version=version).count() == 1


def test_a_staff_session_alone_cannot_publish(staff_without_permissions, db, example):
    version = loader.load_definition(example, activate=True).version

    response = staff_without_permissions.post(f"/admin/prolog_surveys/survey/publish/{version.pk}/")

    assert response.status_code == 403
    version.refresh_from_db()
    assert not version.is_published


def test_loading_needs_add_to_create_and_change_to_re_load(
    db, client, django_user_model, tmp_path, settings, example
):
    """Creating a survey is an add; re-loading one is a change."""
    import copy

    from django.contrib.auth.models import Permission

    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    user = django_user_model.objects.create_user(username="adder", password="pw", is_staff=True)
    # Add alone, deliberately: Django does not read add as implying view, and
    # the form somebody may create a survey with has to open for them.
    user.user_permissions.add(
        Permission.objects.get(codename="add_survey", content_type__app_label="prolog_surveys")
    )
    client.force_login(user)
    (tmp_path / "s.json").write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    post = {"definition_path": str(tmp_path / "s.json"), "action": "load"}

    client.post("/admin/prolog_surveys/survey/verify/", post)
    assert SurveyVersion.objects.count() == 1, "add is enough to create it"

    edited = copy.deepcopy(example)
    edited["title"]["en"] = "Changed by somebody who may only add"
    (tmp_path / "s.json").write_text(json.dumps(edited), encoding="utf-8")

    client.post("/admin/prolog_surveys/survey/verify/", post)

    version = SurveyVersion.objects.get()
    assert version.definition["title"]["en"] == example["title"]["en"], "change is not implied"


def test_an_out_of_root_path_comes_back_by_a_redirect_too(admin_login, db, tmp_path, settings):
    """The one outcome that still rendered on its POST: Back offered to send
    the form again, which is what started this."""
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]

    response = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_path": "/etc/hosts", "action": "load"},
        follow=True,
    )

    assert response.redirect_chain, "an error page a POST produced cannot be gone back to"
    assert "outside every directory" in response.content.decode()


# --- the same two things, from a shell ---------------------------------------


def test_publish_version_command(db, example, capsys):
    version = loader.load_definition(example, activate=True).version

    call_command("publish_version", example["slug"])

    version.refresh_from_db()
    assert version.is_published and not version.is_mutable
    assert "published" in capsys.readouterr().out

    call_command("publish_version", example["slug"], "--survey-version", version.version)

    assert "already published" in capsys.readouterr().out


def test_load_definition_discard_responses_flag(db, example, tmp_path, capsys):
    import copy

    path = tmp_path / "s.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    version = loader.load_file(path, activate=True).version
    make_response(version, language="en")
    edited = copy.deepcopy(example)
    edited["title"]["en"] = "Corrected title"
    path.write_text(json.dumps(edited), encoding="utf-8")

    with pytest.raises(CommandError):
        call_command("load_definition", str(path))
    version.refresh_from_db()
    assert version.definition["title"]["en"] == example["title"]["en"]

    call_command("load_definition", str(path), "--discard-responses")

    version.refresh_from_db()
    assert version.definition["title"]["en"] == "Corrected title"
    assert not SurveyResponse.objects.filter(survey_version=version).exists()


def test_startup_says_a_version_has_responses_rather_than_calling_it_invalid(
    db, example, tmp_path, settings, capsys
):
    import copy

    path = tmp_path / "s.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    version = loader.load_file(path, activate=True).version
    make_response(version, language="en")
    edited = copy.deepcopy(example)
    edited["title"]["en"] = "Corrected title"
    path.write_text(json.dumps(edited), encoding="utf-8")

    with pytest.raises(CommandError):
        call_command("load_definitions")

    err = capsys.readouterr().err
    assert "response(s)" in err and "--discard-responses" in err
    assert "invalid definition" not in err


# --- an uploaded file, which the browser sends once --------------------------


def _upload(example, name="uploaded.json"):
    import io as _io

    f = _io.BytesIO(json.dumps(example).encode())
    f.name = name
    return f


def test_verifying_an_upload_then_loading_it_works(admin_login, db, example):
    """A browser does not send an uploaded file twice, so Verify used to eat
    it and Load answered "choose a mounted definition or upload one"."""
    verified = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_file": _upload(example), "action": "verify"},
        follow=True,
    ).content.decode()

    assert "No errors and no warnings" in verified
    assert "uploaded.json" in verified, "the page says which file it is holding"

    admin_login.post(
        "/admin/prolog_surveys/survey/verify/", {"uploaded": "1", "action": "load"}, follow=True
    )

    version = SurveyVersion.objects.get()
    assert version.survey.slug == example["slug"]
    assert version.source == "upload:uploaded.json"


def test_a_loaded_upload_is_not_held_afterwards(admin_login, db, example):
    """Otherwise a later press with an empty form loads a file nobody chose."""
    admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_file": _upload(example), "action": "verify"},
    )
    admin_login.post(
        "/admin/prolog_surveys/survey/verify/", {"uploaded": "1", "action": "load"}, follow=True
    )

    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/", {"uploaded": "1", "action": "load"}, follow=True
    ).content.decode()

    assert "no longer held" in body
    assert SurveyVersion.objects.count() == 1


def test_an_upload_is_only_used_when_the_form_says_so(admin_login, db, example):
    """The hidden field is what says "the file I just verified"; without it an
    empty form is an empty form."""
    admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_file": _upload(example), "action": "verify"},
    )

    body = admin_login.post(
        "/admin/prolog_surveys/survey/verify/", {"action": "load"}, follow=True
    ).content.decode()

    assert "Choose a mounted definition or upload one" in body
    assert not SurveyVersion.objects.exists()


def test_a_chosen_file_replaces_the_one_being_held(admin_login, db, example, tmp_path, settings):
    import copy

    other = copy.deepcopy(example)
    other["slug"] = "second-instrument"
    admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_file": _upload(example), "action": "verify"},
    )

    admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"uploaded": "1", "definition_file": _upload(other, "other.json"), "action": "load"},
        follow=True,
    )

    assert Survey.objects.get().slug == "second-instrument"


def test_an_upload_outcome_is_a_get_like_every_other(admin_login, db, example):
    response = admin_login.post(
        "/admin/prolog_surveys/survey/verify/",
        {"definition_file": _upload(example), "action": "verify"},
    )

    assert response.status_code == 302, "no page a POST produced, uploads included"
