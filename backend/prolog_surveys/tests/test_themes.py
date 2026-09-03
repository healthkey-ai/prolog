"""Phase 5: theme registry, contrast check, theme API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from prolog_surveys import legal
from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.tests.conftest import example_definition
from prolog_surveys.themes import registry, validate_theme
from prolog_surveys.themes.contrast import contrast_ratio, palette_warnings

REPO_ROOT = Path(__file__).resolve().parents[3]
THEMES = REPO_ROOT / "themes"


@pytest.fixture(autouse=True)
def theme_dirs(settings):
    settings.PROLOG_THEME_DIRS = [str(THEMES)]
    registry.reload()
    yield
    registry.reload()


def write_theme(directory: Path, **overrides) -> Path:
    base = json.loads((THEMES / "default" / "theme.json").read_text())
    base.pop("$schema", None)
    base.update(overrides)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "theme.json").write_text(json.dumps(base))
    return directory


def test_contrast_math():
    assert round(contrast_ratio("#000", "#fff"), 1) == 21.0
    assert contrast_ratio("#ffffff", "#ffffff") == 1.0
    assert contrast_ratio("rgb(0,0,0)", "#fff") is None
    warnings = palette_warnings({"ink": "#999999", "surface": "#ffffff"})
    assert warnings and "ink on surface" in warnings[0]


def test_contrast_checks_cover_ground_for_primary_error_success():
    """THM-8 / the theme manual: primary, error and success are drawn on the
    page ground as well as on cards, so a primary that only reads on white
    must be warned about."""
    palette = {
        **json.loads((THEMES / "default" / "theme.json").read_text())["colors"]["light"],
        "primary": "#6a8f85",
        "ground": "#8fa8a1",
    }
    warnings = palette_warnings(palette)
    assert any(w.startswith("primary on ground") for w in warnings), warnings
    for fg in ("error", "success"):
        assert any(
            w.startswith(f"{fg} on ground") for w in palette_warnings({**palette, fg: "#8a9f9a"})
        )


def test_partial_dark_palette_is_checked_as_light_overridden_by_dark(tmp_path):
    """The runner renders light ∪ dark under prefers-color-scheme: dark, so a
    dark palette that only sets `ground` must be checked against the light ink."""
    light = json.loads((THEMES / "default" / "theme.json").read_text())["colors"]["light"]
    write_theme(
        tmp_path / "dim",
        code="dim",
        color_scheme="light-dark",
        colors={"light": light, "dark": {"ground": "#000000"}},
    )
    _, issues = validate_theme(tmp_path / "dim")
    dark = [i.message for i in issues if i.code == "contrast" and i.path == "$.colors.dark"]
    assert any(w.startswith("ink on ground") for w in dark), [str(i) for i in issues]
    # A pair the dark palette does not touch is reported once, under light.
    write_theme(
        tmp_path / "pale",
        code="pale",
        color_scheme="light-dark",
        colors={"light": {**light, "ink_soft": "#bbbbbb"}, "dark": {"ground": "#f2f7f5"}},
    )
    _, issues = validate_theme(tmp_path / "pale")
    paths = [i.path for i in issues if i.code == "contrast" and "ink_soft on surface" in i.message]
    assert paths == ["$.colors.light"]


def test_builtin_themes_validate():
    for code in ("default", "contrast"):
        data, issues = validate_theme(THEMES / code)
        assert data["code"] == code
        assert not [i for i in issues if i.level == "error"], [str(i) for i in issues]
        assert not [i for i in issues if i.code == "contrast"], [str(i) for i in issues]


def test_registry_loads_and_resolves():
    themes = registry.all()
    assert {"default", "contrast"} <= set(themes)
    assert registry.resolve("contrast").code == "contrast"
    assert registry.resolve("nope").code == "default"
    assert registry.resolve(None).code == "default"


def test_unknown_theme_logged_once_until_reload(caplog):
    registry.resolve("nope")
    registry.resolve("nope")
    registry.resolve("other")
    assert caplog.text.count("unknown theme code") == 2
    registry.reload()
    registry.resolve("nope")
    assert caplog.text.count("unknown theme code") == 3


def test_invalid_theme_rejected(tmp_path, settings, caplog):
    write_theme(tmp_path / "broken", code="broken", colors={"light": {"primary": "#000"}})
    settings.PROLOG_THEME_DIRS = [str(THEMES), str(tmp_path)]
    registry.reload()
    assert "broken" not in registry.all()
    assert "rejected" in caplog.text


def test_missing_asset_is_an_error(tmp_path):
    write_theme(tmp_path / "t", code="t", assets={"logo": "nope.svg"})
    _, issues = validate_theme(tmp_path / "t")
    assert any(i.code == "asset" for i in issues)


def test_low_contrast_is_a_warning(tmp_path, settings):
    write_theme(
        tmp_path / "pale",
        code="pale",
        colors={
            "light": {
                **json.loads((THEMES / "default" / "theme.json").read_text())["colors"]["light"],
                "ink_soft": "#bbbbbb",
            }
        },
    )
    settings.PROLOG_THEME_DIRS = [str(THEMES), str(tmp_path)]
    registry.reload()
    theme = registry.get("pale")
    assert theme is not None
    assert any("ink_soft on surface" in w for w in theme.warnings)


def test_register_theme_command(capsys, tmp_path):
    call_command("register_theme", str(THEMES / "contrast"))
    assert "OK" in capsys.readouterr().out
    write_theme(tmp_path / "bad", code="bad", assets={"logo": "../../etc/passwd"})
    with pytest.raises(CommandError):
        call_command("register_theme", str(tmp_path / "bad"))


def test_theme_api(api_client, db):
    r = api_client.get("/api/run/themes/contrast/")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "contrast"
    # Asset URLs carry a content version so a replaced file gets a new URL.
    assert body["assets"]["logo"].startswith(
        "http://testserver/api/run/themes/contrast/assets/logo.svg?v="
    )
    assert body["warnings"] == []
    assert api_client.get("/api/run/themes/nope/").status_code == 404


def test_theme_assets_served_safely(api_client, db):
    r = api_client.get("/api/run/themes/contrast/assets/logo.svg")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("image/svg+xml")
    assert b"<svg" in b"".join(r.streaming_content)
    assert (
        api_client.get("/api/run/themes/contrast/assets/theme.json").status_code == 404
    )  # not an asset type
    assert (
        api_client.get("/api/run/themes/contrast/assets/../default/theme.json").status_code == 404
    )
    assert (
        api_client.get("/api/run/themes/contrast/assets/%2e%2e/default/theme.json").status_code
        == 404
    )
    assert api_client.get("/api/run/themes/contrast/assets/missing.svg").status_code == 404
    # An embedded NUL is a path the OS refuses (ValueError from lstat): a 404
    # like every other malformed path, never a 500 on an unthrottled endpoint.
    assert api_client.get("/api/run/themes/contrast/assets/logo%00.svg").status_code == 404
    assert registry.get("contrast").asset_path("logo\x00.svg") is None


def test_theme_assets_are_immutable_only_under_their_versioned_url(api_client, db):
    """The theme document links ``?v=<content hash>``; only that URL may be
    cached for a year without revalidation. The bare (or stale) URL revalidates
    with an ETag, so a replaced logo or font reaches returning participants."""
    logo = api_client.get("/api/run/themes/contrast/").json()["assets"]["logo"]
    _, version = logo.split("?v=")
    r = api_client.get(f"/api/run/themes/contrast/assets/logo.svg?v={version}")
    assert r.status_code == 200 and "immutable" in r["Cache-Control"]
    assert r["ETag"] == f'"{version}"'
    for url in (
        "/api/run/themes/contrast/assets/logo.svg",
        "/api/run/themes/contrast/assets/logo.svg?v=stale",
    ):
        r = api_client.get(url)
        assert r.status_code == 200 and "immutable" not in r["Cache-Control"], url
        assert "max-age=" in r["Cache-Control"] and r["ETag"] == f'"{version}"'
    r = api_client.get(
        "/api/run/themes/contrast/assets/logo.svg", HTTP_IF_NONE_MATCH=f'"{version}"'
    )
    assert r.status_code == 304


def test_definition_reports_resolved_theme(api_client, db, caplog):
    doc = example_definition()
    doc["theme"] = "does-not-exist"
    load_definition(doc, activate=True)
    r = api_client.get("/api/run/surveys/sample-wellbeing/")
    assert r.json()["theme_code"] == "default"
    assert "unknown theme code" in caplog.text
    doc["theme"] = "contrast"
    doc["version"] = "1.1"
    load_definition(doc, activate=True)
    assert api_client.get("/api/run/surveys/sample-wellbeing/").json()["theme_code"] == "contrast"


def test_malformed_theme_json_is_skipped(tmp_path, settings, caplog):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "theme.json").write_text("{not json")
    _, issues = validate_theme(tmp_path / "bad")
    assert [i.code for i in issues] == ["json"] and issues[0].level == "error"
    settings.PROLOG_THEME_DIRS = [str(THEMES), str(tmp_path)]
    registry.reload()  # must not raise
    assert "bad" not in registry.all() and "default" in registry.all()
    assert "rejected" in caplog.text


# --- deployment-supplied legal pages -----------------------------------------


@pytest.fixture
def legal_dir(tmp_path, settings):
    (tmp_path / "privacy.md").write_text("# Privacy\n\nWe keep little.\n", encoding="utf-8")
    (tmp_path / "privacy.es.md").write_text("# Privacidad\n\nGuardamos poco.\n", encoding="utf-8")
    settings.PROLOG_LEGAL_DIRS = [str(tmp_path)]
    return tmp_path


def test_legal_page_is_served_in_the_requested_language(api_client, legal_dir):
    body = api_client.get("/api/run/legal/privacy/?lang=es").json()

    assert body["page"] == "privacy" and body["language"] == "es"
    assert "Privacidad" in body["markdown"]


def test_legal_page_falls_back_to_the_untranslated_file(api_client, legal_dir):
    """A respondent reading a language nobody translated the notice into gets
    the notice, not nothing."""
    body = api_client.get("/api/run/legal/privacy/?lang=fr").json()

    assert body["language"] == "" and "We keep little" in body["markdown"]


def test_a_regional_tag_finds_the_base_language(api_client, legal_dir):
    assert api_client.get("/api/run/legal/privacy/?lang=es-419").json()["language"] == "es"


def test_a_page_the_deployment_did_not_mount_is_404(api_client, legal_dir):
    assert api_client.get("/api/run/legal/terms/").status_code == 404


def test_no_legal_dirs_means_no_pages(api_client, settings):
    settings.PROLOG_LEGAL_DIRS = []

    assert api_client.get("/api/run/legal/privacy/").status_code == 404
    assert legal.available() == set()


def test_a_page_name_cannot_walk_out_of_the_directory(tmp_path, settings):
    """The name reaches the filesystem, so it is matched against a pattern
    rather than sanitised."""
    (tmp_path / "secret.md").write_text("private", encoding="utf-8")
    settings.PROLOG_LEGAL_DIRS = [str(tmp_path / "public")]
    (tmp_path / "public").mkdir()

    assert legal.find("../secret") is None
    assert legal.find("..%2Fsecret") is None
    assert legal.find("") is None


def test_an_oversized_page_is_not_served(tmp_path, settings):
    """A document, not a download."""
    (tmp_path / "privacy.md").write_text("x" * (legal.MAX_BYTES + 1), encoding="utf-8")
    settings.PROLOG_LEGAL_DIRS = [str(tmp_path)]

    assert legal.find("privacy") is None


def test_the_definition_says_which_pages_exist(db, api_client, example, legal_dir):
    """The runner renders a link only for a page that is there: a link to a
    404 is worst on the screen that asks for an email address."""
    from prolog_surveys.definitions.loader import load_definition

    version = load_definition(example, activate=True).version
    body = api_client.get(f"/api/run/surveys/{version.survey.slug}/").json()

    assert body["legal_pages"] == ["privacy"]
