"""Django system checks registered by the app."""

from __future__ import annotations

import pytest
from django.core.checks import Error, run_checks
from django.db import connection

from prolog_surveys import checks, conf
from prolog_surveys.models import SurveyInvitation, SurveyResponse


def _ids(messages):
    return sorted(m.id for m in messages)


def test_retention_days_must_be_positive(settings):
    settings.PROLOG_ABANDONED_RESPONSE_DAYS = 0
    assert _ids(checks.check_settings(None)) == ["prolog_surveys.E001"]
    settings.PROLOG_ABANDONED_RESPONSE_DAYS = "90"
    assert _ids(checks.check_settings(None)) == ["prolog_surveys.E001"]
    settings.PROLOG_ABANDONED_RESPONSE_DAYS = 1
    assert checks.check_settings(None) == []


def test_settings_check_is_registered(settings):
    settings.PROLOG_ABANDONED_RESPONSE_DAYS = -3
    assert "prolog_surveys.E001" in _ids(run_checks())


@pytest.mark.django_db
def test_participant_columns_check_passes_on_a_migrated_database():
    assert checks.check_participant_columns(None, databases=["default"]) == []


@pytest.mark.django_db
def test_participant_columns_check_is_a_no_op_without_databases():
    assert checks.check_participant_columns(None, databases=None) == []


@pytest.mark.django_db(transaction=False)
@pytest.mark.skipif(not conf.is_integrated(), reason="integrated profile only")
def test_participant_columns_missing_is_reported():
    # A database migrated in the standalone profile has 0005 recorded as
    # applied and no participant columns; the switch must not go unnoticed.
    # The DDL runs inside the test transaction and is rolled back with it.
    with connection.cursor() as cursor:
        for model in (SurveyResponse, SurveyInvitation):
            cursor.execute(f'ALTER TABLE "{model._meta.db_table}" DROP COLUMN "participant_id"')
    messages = checks.check_participant_columns(None, databases=["default"])
    assert [type(m) for m in messages] == [Error, Error]
    assert _ids(messages) == ["prolog_surveys.E002", "prolog_surveys.E002"]
    assert all("migrate prolog_surveys zero --fake" in m.hint for m in messages)
    assert "prolog_surveys.E002" in _ids(run_checks(databases=["default"]))
