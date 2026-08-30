from django.core.management.base import BaseCommand, CommandError

from ...definitions.loader import discover, validate_definition
from ...definitions.schema import read_json
from ...definitions.validate import has_errors
from ._definitions import report


class Command(BaseCommand):
    help = "Validate survey definition files (schema + semantic rules) without writing anything."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Definition files or directories")
        parser.add_argument("--profile", choices=["standalone", "integrated"], default=None)

    def handle(self, *args, **options):
        files = discover(options["paths"])
        if not files:
            raise CommandError("no definition files found")
        failed = 0
        for path in files:
            issues = validate_definition(read_json(path), profile=options["profile"])
            report(self, issues)
            if has_errors(issues):
                failed += 1
                self.stderr.write(self.style.ERROR(f"INVALID {path}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"OK {path}"))
        if failed:
            raise CommandError(f"{failed} definition(s) invalid")
