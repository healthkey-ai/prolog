"""Django system checks (registered from AppConfig.ready).

``check_settings`` runs with every ``manage.py`` command; ``check_participant_
columns`` is a database check, so it runs where a connection is expected:
``migrate`` (the point where a profile switch would otherwise go unnoticed)
and ``check --database default``.
"""

from __future__ import annotations

from django.core.checks import Error, Tags, register
from django.db import connections
from django.db.migrations.recorder import MigrationRecorder

from . import conf

PARTICIPANT_MIGRATION = ("prolog_surveys", "0005_participant")


@register(Tags.compatibility)
def check_settings(app_configs, **kwargs):
    days = conf.get("PROLOG_ABANDONED_RESPONSE_DAYS")
    if not isinstance(days, int) or isinstance(days, bool) or days < 1:
        return [
            Error(
                f"PROLOG_ABANDONED_RESPONSE_DAYS must be an integer of at least 1, got {days!r}",
                hint="With 0 (or a negative value) purge_abandoned_responses would delete every "
                "in-progress response, including the ones being answered right now.",
                id="prolog_surveys.E001",
            )
        ]
    return []


@register(Tags.database)
def check_participant_columns(app_configs, databases=None, **kwargs):
    """The participant columns exist when the integrated profile expects them.

    ``0005_participant`` adds them only while PROLOG_PARTICIPANT_MODEL is set.
    A database migrated in the standalone profile records that migration as
    applied with no columns; switching the profile afterwards leaves
    ``migrate`` with nothing to do while every response and invitation query
    fails. Report it with the remediation instead.
    """
    if not conf.participant_model() or not databases:
        return []
    from .models import SurveyInvitation, SurveyResponse

    errors = []
    for alias in databases:
        connection = connections[alias]
        if PARTICIPANT_MIGRATION not in MigrationRecorder(connection).applied_migrations():
            continue  # a pending migrate will add the columns
        with connection.cursor() as cursor:
            existing = set(connection.introspection.table_names(cursor))
            for model in (SurveyResponse, SurveyInvitation):
                table = model._meta.db_table
                if table not in existing:
                    continue
                columns = {
                    column.name
                    for column in connection.introspection.get_table_description(cursor, table)
                }
                if "participant_id" not in columns:
                    errors.append(
                        Error(
                            f"{table} has no participant_id column although "
                            "PROLOG_PARTICIPANT_MODEL is set: migration 0005_participant "
                            "was applied in the standalone profile.",
                            hint="Re-apply it under the integrated settings: "
                            "`manage.py migrate prolog_surveys 0004 --fake --skip-checks` "
                            "then `manage.py migrate`.",
                            obj=alias,
                            id="prolog_surveys.E002",
                        )
                    )
    return errors
