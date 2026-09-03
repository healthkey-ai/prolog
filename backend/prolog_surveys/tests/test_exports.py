"""Phase 6: exports, retention purge, health."""

from __future__ import annotations

import csv
import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.exports import (
    safe_cell,
    translation_rows,
    write_contacts,
    write_responses,
    write_translations,
)
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


def test_export_commands(version, submitted, api_client, tmp_path, capsys):
    api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    )
    call_command("export_responses", "sample-wellbeing", "--out", str(tmp_path / "r.csv"))
    call_command("export_contacts", "sample-wellbeing", "--out", str(tmp_path / "c.csv"))
    rows = list(csv.reader(io.StringIO((tmp_path / "r.csv").read_text())))
    assert len(rows) == 2 and rows[1][4] == "submitted"
    assert "someone@example.org" in (tmp_path / "c.csv").read_text()
    call_command(
        "export_responses",
        "sample-wellbeing",
        "--include-in-progress",
        "--out",
        str(tmp_path / "all.csv"),
    )
    rows = list(csv.reader(io.StringIO((tmp_path / "all.csv").read_text())))
    assert len(rows) == 3
    assert sorted(r[4] for r in rows[1:]) == ["in_progress", "submitted"]
    call_command("export_responses", "sample-wellbeing")
    assert (
        capsys.readouterr().out.count("\n") == 2
    )  # stdout works too, default excludes in-progress


# --- spreadsheet formula injection (safe_cell) -----------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("=1+1", "'=1+1"),
        ("+x", "'+x"),
        ("-2", "'-2"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\tcmd", "'\tcmd"),
        ("\rcmd", "'\rcmd"),
        ("plain text, all good", "plain text, all good"),
        ("", ""),
    ],
)
def test_safe_cell_neutralises_leading_formula_characters(text, expected):
    assert safe_cell(text) == expected


def test_exports_apply_safe_cell_to_free_text_and_emails(version, api_client):
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
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
            "symptoms": {"options": ["other"], "other_text": "-2"},
            "symptom_impact": {"ratings": {"other": 4}},
            "daily_activities": {"ratings": {"walking": 1, "housework": 2, "socialising": 3}},
            "outcome_ranking": {
                "order": ["independence", "energy", "side_effects", "fewer_visits"]
            },
            "support_wanted": {"options": ["peer"]},
            "told_clinician": {"option": "no"},
            "anything_else": {"text": '=HYPERLINK("x")'},
        },
    )
    assert (
        api_client.post(
            f"/api/run/responses/{rid}/contact/", {"email": "+x@example.org"}, format="json"
        ).status_code
        == 204
    )
    assert api_client.post(f"/api/run/responses/{rid}/submit/").status_code == 200
    out = io.StringIO()
    write_responses(version, out)
    rows = list(csv.reader(io.StringIO(out.getvalue())))
    record = dict(zip(rows[0], rows[1], strict=True))
    assert record["anything_else"] == '\'=HYPERLINK("x")'
    assert record["symptoms.other_text"] == "'-2"
    out = io.StringIO()
    write_contacts(version, out)
    rows = list(csv.reader(io.StringIO(out.getvalue())))
    assert dict(zip(rows[0], rows[1], strict=True))["email"] == "'+x@example.org"


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


# --- translation review sheet ------------------------------------------------


def test_translation_rows_pair_the_languages_in_presentation_order(example):
    rows = list(translation_rows(example, "es"))

    assert rows[0][0] == "$.title"
    assert rows[0][2] == example["title"]["en"]
    assert rows[0][3] == example["title"]["es"]
    # every translatable string, not only the ones that happen to be translated
    from prolog_surveys.definitions.validate import walk_i18n

    assert [r[0] for r in rows] == [path for path, _ in walk_i18n(example)]


def test_a_missing_translation_is_an_empty_cell_not_a_missing_row(example):
    """The gaps are the point: a shorter file hides what nobody has translated."""
    del example["sections"][0]["questions"][0]["text"]["es"]

    rows = list(translation_rows(example, "es"))
    row = next(r for r in rows if r[0] == "$.sections[0].questions[0].text")

    assert row[2] and row[3] == ""
    assert len(rows) == len(list(translation_rows(example, "en")))


def test_the_status_travels_with_the_text(example):
    example["translation_status"]["es"] = "machine"

    assert {r[1] for r in translation_rows(example, "es")} == {"machine"}


def test_against_picks_the_column_to_compare(example):
    rows = list(translation_rows(example, "es", against="fr"))

    assert rows[0][2] == example["title"]["fr"]


def test_csv_is_not_a_formula_injection_route(example):
    """Survey text is free text, and a reviewer opens this in a spreadsheet."""
    example["title"]["es"] = "=cmd|' /c calc'!A1"

    out = io.StringIO()
    write_translations(example, out, language="es")
    body = out.getvalue()

    assert "'=cmd" in body


def test_markdown_escapes_a_pipe_so_the_columns_survive(example):
    example["title"]["es"] = "uno | dos"

    out = io.StringIO()
    write_translations(example, out, language="es", markdown=True)
    line = next(ln for ln in out.getvalue().splitlines() if ln.startswith("| $.title "))

    import re

    assert r"uno \| dos" in line
    # split on delimiters only — an escaped pipe is content, not a column break
    assert len(re.split(r"(?<!\\)\|", line)) - 2 == 4  # leading and trailing empties


def test_export_translations_command(version, tmp_path, capsys):
    call_command(
        "export_translations",
        "sample-wellbeing",
        "--language",
        "es",
        "--out",
        str(tmp_path / "es.csv"),
    )
    rows = list(csv.reader(io.StringIO((tmp_path / "es.csv").read_text())))

    assert rows[0] == ["path", "status", "en", "es"]
    assert len(rows) > 1
    assert "string(s)" in capsys.readouterr().err


def test_export_translations_refuses_a_language_the_survey_does_not_offer(version):
    with pytest.raises(CommandError, match="does not offer 'de'"):
        call_command("export_translations", "sample-wellbeing", "--language", "de")


def test_export_translations_refuses_comparing_a_language_with_itself(version):
    with pytest.raises(CommandError, match="must differ"):
        call_command(
            "export_translations", "sample-wellbeing", "--language", "es", "--against", "es"
        )


def test_export_translations_says_when_nothing_has_been_reviewed(db, example, capsys):
    """A reviewer opening a machine file should know that is what it is."""
    example["translation_status"]["es"] = "machine"
    load_definition(example)

    call_command(
        "export_translations",
        "sample-wellbeing",
        "--language",
        "es",
        "--survey-version",
        example["version"],
    )

    assert "machine-translated" in capsys.readouterr().err
