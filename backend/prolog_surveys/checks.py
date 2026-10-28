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

PARTICIPANT_MIGRATION = ("prolog_surveys", "0001_initial")


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

    ``0001_initial`` adds them only while PROLOG_PARTICIPANT_MODEL is set.
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
                            "PROLOG_PARTICIPANT_MODEL is set: migration 0001_initial "
                            "was applied in the standalone profile.",
                            hint="Re-apply it under the integrated settings: "
                            "`manage.py migrate prolog_surveys zero --fake --skip-checks` "
                            "then `manage.py migrate`.",
                            obj=alias,
                            id="prolog_surveys.E002",
                        )
                    )
    return errors


@register(Tags.database)
def check_patient_column(app_configs, databases=None, **kwargs):
    """Detect enabling patient linkage after 0004 ran without a host model."""
    if not conf.patient_model() or not databases:
        return []
    from .models import SurveyLinkedContact

    errors = []
    for alias in databases:
        connection = connections[alias]
        applied = MigrationRecorder(connection).applied_migrations()
        if ("prolog_surveys", "0004_linked_contact_patient") not in applied:
            continue
        with connection.cursor() as cursor:
            table = SurveyLinkedContact._meta.db_table
            if table not in connection.introspection.table_names(cursor):
                continue
            columns = connection.introspection.get_table_description(cursor, table)
            if "patient_id" not in {column.name for column in columns}:
                errors.append(
                    Error(
                        f"{table} has no patient_id column although patient linkage is enabled.",
                        hint="Add the nullable patient FK in a host migration before enabling linkage; "
                        "0004_linked_contact_patient previously ran without a patient model.",
                        obj=alias,
                        id="prolog_surveys.E003",
                    )
                )
    return errors
