# Integrated profile: a merge candidate names two of the host's participant rows
# (CON-4, open decision 7), so like 0005 and 0006 the table is created in both
# profiles for a shared migration state while the foreign keys exist only where
# there is something to point at.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

PARTICIPANT_MODEL = getattr(settings, "PROLOG_PARTICIPANT_MODEL", None)


def _participant_fields():
    """Built lazily: the fields cannot be constructed without a target."""
    if not PARTICIPANT_MODEL:
        return []
    return [
        (
            "minted",
            models.ForeignKey(
                help_text="The participant the response is bound to.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="prolog_merge_candidates",
                to=PARTICIPANT_MODEL,
            ),
        ),
        (
            "existing",
            models.ForeignKey(
                help_text="The participant the address already belongs to.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="prolog_merge_claims",
                to=PARTICIPANT_MODEL,
            ),
        ),
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("prolog_surveys", "0006_minted_participant"),
    ]
    if PARTICIPANT_MODEL:
        dependencies.append(migrations.swappable_dependency(PARTICIPANT_MODEL))

    operations = [
        migrations.CreateModel(
            name="ParticipantMergeCandidate",
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
                    "resolved_at",
                    models.DateTimeField(
                        blank=True, help_text="When a human settled this pair.", null=True
                    ),
                ),
            ]
            + _participant_fields(),
            options={
                "indexes": [
                    models.Index(fields=["resolved_at"], name="prolog_surv_resolve_f861d2_idx")
                ],
            },
        ),
    ]
