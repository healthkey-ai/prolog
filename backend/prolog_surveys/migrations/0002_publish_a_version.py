"""Publishing a version freezes its content; until then it can be re-loaded.

A version is loaded, activated, answered a few times to see how it reads,
corrected, and loaded again. Those responses are test data, and that loop is how
an instrument gets right. Publishing is the deliberate end of it: from then on
the content cannot change, because a response records which version it answered.

``published_at`` used to record activation, which is a different event and now
has the name that says so. Existing versions are left unpublished: a deployment
that has been running one for months can publish it deliberately, which is
better than this migration deciding on its behalf that it is frozen.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("prolog_surveys", "0001_initial")]

    operations = [
        migrations.RenameField(
            model_name="surveyversion", old_name="published_at", new_name="activated_at"
        ),
        migrations.AlterField(
            model_name="surveyversion",
            name="activated_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When this version was last made the active one.",
            ),
        ),
        migrations.AddField(
            model_name="surveyversion",
            name="published_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "When this version's content was frozen. Until then it can be "
                    "re-loaded, and the responses against it are test data."
                ),
            ),
        ),
    ]
