from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ...definitions.validate import has_errors
from ...themes import validate_theme
from ._definitions import report


class Command(BaseCommand):
    help = "Validate a theme directory (schema, assets, contrast) without writing anything."

    def add_arguments(self, parser):
        parser.add_argument(
            "directories", nargs="+", help="Theme directories containing theme.json"
        )

    def handle(self, *args, **options):
        failed = 0
        for d in options["directories"]:
            data, issues = validate_theme(Path(d))
            report(self, issues)
            if has_errors(issues):
                failed += 1
                self.stderr.write(self.style.ERROR(f"INVALID {d}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"OK {d} (theme '{data.get('code')}')"))
        if failed:
            raise CommandError(f"{failed} theme(s) invalid")
