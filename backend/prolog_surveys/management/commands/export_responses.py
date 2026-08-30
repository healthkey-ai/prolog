import sys

from django.core.management.base import BaseCommand

from ...exports import write_responses
from ._versions import resolve_version


class Command(BaseCommand):
    help = "Export responses of a survey version as CSV (one row per response). Contacts are never included."

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--survey-version", default=None, help="Defaults to the active version")
        parser.add_argument("--format", choices=["csv"], default="csv")
        parser.add_argument("--out", default="-", help="File path or - for stdout")
        parser.add_argument("--include-in-progress", action="store_true")

    def handle(self, *args, **options):
        version = resolve_version(options["slug"], options["survey_version"])
        out = (
            sys.stdout
            if options["out"] == "-"
            else open(options["out"], "w", newline="", encoding="utf-8")
        )
        try:
            n = write_responses(version, out, submitted_only=not options["include_in_progress"])
        finally:
            if out is not sys.stdout:
                out.close()
        self.stderr.write(f"exported {n} response(s) of {version}")
