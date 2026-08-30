import sys

from django.core.management.base import BaseCommand

from ...exports import write_contacts
from ._versions import resolve_version


class Command(BaseCommand):
    help = "Export contact-capture emails of a survey version as CSV (separate from responses by design)."

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--survey-version", default=None)
        parser.add_argument("--out", default="-")

    def handle(self, *args, **options):
        version = resolve_version(options["slug"], options["survey_version"])
        out = (
            sys.stdout
            if options["out"] == "-"
            else open(options["out"], "w", newline="", encoding="utf-8")
        )
        try:
            n = write_contacts(version, out)
        finally:
            if out is not sys.stdout:
                out.close()
        self.stderr.write(f"exported {n} contact(s) of {version}")
