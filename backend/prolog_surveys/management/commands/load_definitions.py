from django.core.management.base import BaseCommand
from django.db import DataError, IntegrityError

from ...definitions.loader import DefinitionError, discover, load_file
from ._definitions import report


class Command(BaseCommand):
    help = "Load every definition found in PROLOG_DEFINITION_DIRS as a draft (run at startup)."

    def handle(self, *args, **options):
        files = discover()
        if not files:
            self.stdout.write("no definitions found in PROLOG_DEFINITION_DIRS")
            return
        skipped = 0
        for path in files:
            try:
                result = load_file(path)
            except DefinitionError as exc:
                report(self, exc.issues)
                self.stderr.write(self.style.ERROR(f"skipped invalid definition: {path}"))
                skipped += 1
                continue
            except (DataError, IntegrityError) as exc:
                # A value the schema admits but the database refuses (or a
                # concurrent load). Each file loads in its own transaction, so
                # the others still load and the container still starts.
                self.stderr.write(self.style.ERROR(f"skipped {path}: {exc}"))
                skipped += 1
                continue
            report(self, result.warnings)
            state = "created" if result.created else ("updated" if result.changed else "unchanged")
            self.stdout.write(f"{state}: {result.version} <- {path}")
        if skipped:
            self.stderr.write(
                self.style.ERROR(f"{skipped} of {len(files)} definition(s) skipped (see above)")
            )
