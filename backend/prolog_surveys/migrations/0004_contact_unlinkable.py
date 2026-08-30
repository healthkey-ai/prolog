"""Contact rows carry no join key to a response (CON-3).

The table is recreated: a sequence primary key and a timestamp both paired a
contact with the response whose capture marker was written in the same
request. No deployment predates this migration, so nothing is migrated over.
"""

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("prolog_surveys", "0003_invitations")]

    operations = [
        migrations.DeleteModel(name="SurveyContact"),
        migrations.CreateModel(
            name="SurveyContact",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("email", models.EmailField(max_length=254)),
                ("language", models.CharField(blank=True, default="", max_length=12)),
                (
                    "consent_text",
                    models.TextField(help_text="The notice shown when the address was given."),
                ),
                ("captured_on", models.DateField(default=django.utils.timezone.localdate)),
                (
                    "survey_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="contacts",
                        to="prolog_surveys.surveyversion",
                    ),
                ),
            ],
            options={"ordering": ["-captured_on"]},
        ),
    ]
