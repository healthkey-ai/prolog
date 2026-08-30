from django.core.management.base import BaseCommand

from ...exports import write_responses
from ._versions import add_version_arguments, csv_output, resolve_version


class Command(BaseCommand):
    help = "Export responses of a survey version as CSV (one row per response). Contacts are never included."

    def add_arguments(self, parser):
        add_version_arguments(parser)
        parser.add_argument("--include-in-progress", action="store_true")

    def handle(self, *args, **options):
        version = resolve_version(options["slug"], options["survey_version"])
        with csv_output(options["out"]) as out:
            n = write_responses(version, out, submitted_only=not options["include_in_progress"])
        self.stderr.write(f"exported {n} response(s) of {version}")
