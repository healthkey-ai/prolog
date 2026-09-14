from django.core.management.base import BaseCommand, CommandError

from ...definitions.loader import read_json
from ...definitions.normalize import normalize
from ...exports import write_translation_matrix, write_translations
from ._versions import csv_output, resolve_version


class Command(BaseCommand):
    help = (
        "Export a survey version's translations side by side for review: one row per "
        "translatable string, the source language and the target language(s) in adjacent "
        "columns. --language all shows every language the instrument offers, which is the "
        "form to keep somewhere people read; a single --language is the sheet a reviewer "
        "works through."
    )

    def add_arguments(self, parser):
        parser.add_argument("slug", nargs="?", help="Omit when using --file")
        parser.add_argument("--survey-version", default=None, help="Defaults to the active version")
        parser.add_argument("--out", default="-", help="File path or - for stdout")
        parser.add_argument(
            "--file",
            default=None,
            help=(
                "Read the definition from this file instead of the database. The strings "
                "are in the file, so keeping a review sheet current needs no deployment."
            ),
        )
        parser.add_argument(
            "--language",
            required=True,
            help=(
                "The language being reviewed, e.g. es. Several, comma-separated, for one "
                "sheet with a column each; 'all' for every language but the source."
            ),
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
        definition, label = self._definition(options)
        offered = definition.get("languages", [])
        against = options["against"] or definition.get("default_language", "en")
        if against not in offered:
            raise CommandError(f"{label} does not offer '{against}'")

        requested = options["language"]
        if requested == "all":
            languages = [lang for lang in offered if lang != against]
            if not languages:
                raise CommandError(f"{label} offers no language other than '{against}'")
        else:
            languages = [lang.strip() for lang in requested.split(",") if lang.strip()]
        for lang in languages:
            if lang not in offered:
                raise CommandError(f"{label} does not offer '{lang}'; it has " + ", ".join(offered))
            if lang == against:
                raise CommandError("--against must differ from --language")

        markdown = options["format"] == "md"
        with csv_output(options["out"]) as out:
            if len(languages) == 1:
                n = write_translations(
                    definition, out, language=languages[0], against=against, markdown=markdown
                )
            else:
                n = write_translation_matrix(
                    definition, out, languages=languages, against=against, markdown=markdown
                )

        status = definition.get("translation_status") or {}
        self.stderr.write(
            f"exported {n} string(s) of {label} — "
            + ", ".join(f"{lang} is '{status.get(lang, 'unset')}'" for lang in languages)
        )
        machine = [lang for lang in languages if status.get(lang) == "machine"]
        if machine:
            self.stderr.write(
                self.style.WARNING(
                    f"{', '.join(machine)} machine-translated: nothing in those columns has "
                    "been reviewed, which is what the review is for."
                )
            )

    def _definition(self, options) -> tuple[dict, str]:
        """The definition to export, from a file or from the database.

        A file needs no database and no deployment, which is what keeping a
        review sheet current off a repository checkout asks for. Normalised
        either way, so both read the document the engine would.
        """
        if options["file"]:
            if options["slug"]:
                raise CommandError("give a slug or --file, not both")
            from pathlib import Path

            path = Path(options["file"])
            try:
                doc = read_json(path)
            except (OSError, ValueError) as exc:
                raise CommandError(f"{path} could not be read: {exc}") from exc
            return normalize(doc), str(path)
        if not options["slug"]:
            raise CommandError("give a survey slug, or --file to read a definition from disk")
        version = resolve_version(options["slug"], options["survey_version"])
        return version.cached_definition, str(version)
