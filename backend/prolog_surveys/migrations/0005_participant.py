# Integrated profile (DEP-2): the participant foreign keys exist only when the
# host names its participant model. The operations are built from that setting
# so the migration state matches the conditional model fields in both profiles;
# a standalone deployment applies an empty migration.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

PARTICIPANT_MODEL = getattr(settings, "PROLOG_PARTICIPANT_MODEL", None)


class Migration(migrations.Migration):
    dependencies = [
        ("prolog_surveys", "0004_response_inprogress_index"),
    ]
    if PARTICIPANT_MODEL:
        dependencies.append(migrations.swappable_dependency(PARTICIPANT_MODEL))

    operations = (
        [
            migrations.AddField(
                model_name="surveyresponse",
                name="participant",
                field=models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="prolog_survey_responses",
                    to=PARTICIPANT_MODEL,
                ),
            ),
            migrations.AddField(
                model_name="surveyinvitation",
                name="participant",
                field=models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="prolog_survey_invitations",
                    to=PARTICIPANT_MODEL,
                ),
            ),
        ]
        if PARTICIPANT_MODEL
        else []
    )
