from django.core.management.base import BaseCommand

from ...definitions.loader import DefinitionError, discover, load_file
from ._definitions import report


class Command(BaseCommand):
    help = "Load every definition found in PROLOG_DEFINITION_DIRS as a draft (run at startup)."

    def handle(self, *args, **options):
        files = discover()
        if not files:
            self.stdout.write("no definitions found in PROLOG_DEFINITION_DIRS")
            return
        for path in files:
            try:
                result = load_file(path)
            except DefinitionError as exc:
                report(self, exc.issues)
                self.stderr.write(self.style.ERROR(f"skipped invalid definition: {path}"))
                continue
            report(self, result.warnings)
            state = "created" if result.created else ("updated" if result.changed else "unchanged")
            self.stdout.write(f"{state}: {result.version} <- {path}")
