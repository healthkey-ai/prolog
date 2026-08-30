"""Phase 5: theme registry, contrast check, theme API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

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
    assert body["assets"]["logo"].startswith(
        "http://testserver/api/run/themes/contrast/assets/logo.svg"
    )
    assert body["warnings"] == []
    assert api_client.get("/api/run/themes/nope/").status_code == 404


def test_theme_assets_served_safely(api_client, db):
    r = api_client.get("/api/run/themes/contrast/assets/logo.svg")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("image/svg+xml")
    assert "immutable" in r["Cache-Control"]
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
