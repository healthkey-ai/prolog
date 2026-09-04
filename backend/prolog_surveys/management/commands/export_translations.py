from django.core.management.base import BaseCommand, CommandError

from ...exports import write_translations
from ._versions import csv_output, resolve_version


class Command(BaseCommand):
    help = (
        "Export a survey version's translations side by side for review: one row per "
        "translatable string, the source language and the target language in adjacent "
        "columns."
    )

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--survey-version", default=None, help="Defaults to the active version")
        parser.add_argument("--out", default="-", help="File path or - for stdout")
        parser.add_argument(
            "--language",
            required=True,
            help="The language being reviewed, e.g. es",
        )
        parser.add_argument(
            "--against",
            default=None,
            help="The language to show beside it. Defaults to the survey's default language.",
        )
        parser.add_argument(
            "--format",
            choices=["csv", "md"],
            default="csv",
            help="csv opens in a spreadsheet; md renders in a document or a pull request",
        )

    def handle(self, *args, **options):
        version = resolve_version(options["slug"], options["survey_version"])
        definition = version.cached_definition
        language = options["language"]
        if language not in definition.get("languages", []):
            raise CommandError(
                f"'{version.survey.slug}' does not offer '{language}'; it has "
                + ", ".join(definition.get("languages", []))
            )
        against = options["against"] or definition.get("default_language", "en")
        if against not in definition.get("languages", []):
            raise CommandError(f"'{version.survey.slug}' does not offer '{against}'")
        if against == language:
            raise CommandError("--against must differ from --language")

        with csv_output(options["out"]) as out:
            n = write_translations(
                definition,
                out,
                language=language,
                against=against,
                markdown=options["format"] == "md",
            )
        status = (definition.get("translation_status") or {}).get(language, "unset")
        self.stderr.write(f"exported {n} string(s) of {version} — {language} is '{status}'")
        if status == "machine":
            self.stderr.write(
                self.style.WARNING(
                    f"'{language}' is machine-translated: nothing in this file has been "
                    "reviewed, which is what the review is for."
                )
            )
