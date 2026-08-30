"""Operational commands: startup loader resilience, retention guard rails."""

from __future__ import annotations

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from prolog_surveys.models import SurveyResponse, SurveyVersion


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
