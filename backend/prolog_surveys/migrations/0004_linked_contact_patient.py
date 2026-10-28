"""Optional host-patient FK, following the participant links in 0001."""

import django.db.models.deletion
from django.db import migrations, models

from prolog_surveys import conf

PATIENT_MODEL = conf.patient_model()


def _dependency():
    if PATIENT_MODEL == "omop_core.PatientRecord":
        # PatientInfo was renamed here; it does not exist under this model
        # name in omop_core's first migration.
        return [("omop_core", "0104_rename_patientinfo_to_patientrecord")]
    return [(PATIENT_MODEL.split(".")[0], "__first__")] if PATIENT_MODEL else []


class Migration(migrations.Migration):
    dependencies = [("prolog_surveys", "0003_capture_consents"), *_dependency()]
    operations = (
        [
            migrations.AddField(
                model_name="surveylinkedcontact",
                name="patient",
                field=models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="prolog_linked_contacts",
                    to=PATIENT_MODEL,
                ),
            )
        ]
        if PATIENT_MODEL
        else []
    )
