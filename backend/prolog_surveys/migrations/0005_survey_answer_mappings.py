import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("prolog_surveys", "0004_linked_contact_patient")]

    operations = [
        migrations.CreateModel(
            name="SurveyAnswerMapping",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("question_key", models.CharField(max_length=128)),
                (
                    "answer_value",
                    models.TextField(help_text="Raw option key, never a translated label."),
                ),
                ("patient_field", models.CharField(max_length=64)),
                ("mapped_value", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "survey",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="answer_mappings",
                        to="prolog_surveys.survey",
                    ),
                ),
            ],
            options={
                "db_table": "prolog_surveys_surveyanswermap",
                "ordering": ["survey", "question_key", "answer_value", "patient_field"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("survey", "question_key", "answer_value", "patient_field"),
                        name="prolog_answer_mapping_unique",
                    )
                ],
            },
        ),
    ]
