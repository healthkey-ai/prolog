from django.core.management.base import BaseCommand

from ...exports import write_contacts
from ._versions import add_version_arguments, csv_output, resolve_version


class Command(BaseCommand):
    help = "Export contact-capture emails of a survey version as CSV (separate from responses by design)."

    def add_arguments(self, parser):
        add_version_arguments(parser)

    def handle(self, *args, **options):
        version = resolve_version(options["slug"], options["survey_version"])
        with csv_output(options["out"]) as out:
            n = write_contacts(version, out)
        self.stderr.write(f"exported {n} contact(s) of {version}")
