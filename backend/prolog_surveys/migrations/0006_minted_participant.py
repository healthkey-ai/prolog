# Integrated profile (DEP-2/RUN-2): the marker records that PROlog created one of
# the host's participant rows for a respondent who was not signed in. The table
# is always created so both profiles share a migration state; the foreign key
# exists only when the host names a participant model, for the same reason 0005's
# fields do — there is nothing to point at otherwise.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

PARTICIPANT_MODEL = getattr(settings, "PROLOG_PARTICIPANT_MODEL", None)


def _participant_field():
    """Built lazily: the field cannot even be constructed without a target."""
    if not PARTICIPANT_MODEL:
        return []
    return [
        (
            "participant",
            models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="prolog_minted",
                to=PARTICIPANT_MODEL,
            ),
        )
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("prolog_surveys", "0005_participant"),
    ]
    if PARTICIPANT_MODEL:
        dependencies.append(migrations.swappable_dependency(PARTICIPANT_MODEL))

    operations = [
        migrations.CreateModel(
            name="MintedParticipant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "identified_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When this participant gained an account (CON-4).",
                        null=True,
                    ),
                ),
            ]
            + _participant_field(),
            options={
                "indexes": [
                    models.Index(fields=["identified_at"], name="prolog_surv_identif_b36635_idx")
                ],
            },
        ),
    ]
