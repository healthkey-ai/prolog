from django.core.management.base import BaseCommand, CommandError
from django.db import DataError, IntegrityError

from ...definitions.loader import DefinitionError, ResponsesExist, discover, load_file
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
            # Each file loads in its own transaction and every failure below is
            # reported and skipped, so one bad file never stops the others
            # from loading; the command still exits non-zero at the end.
            try:
                result = load_file(path)
            except ResponsesExist as exc:
                # Valid, and deliberately not applied: the version has
                # responses. Saying "invalid definition" would send whoever
                # reads the boot log looking for a schema error there isn't.
                self.stderr.write(
                    self.style.ERROR(
                        f"skipped {path}: {exc.version} has {exc.total} response(s). "
                        "Load it with --discard-responses if they are test data, or bump "
                        "the version in the file."
                    )
                )
                skipped += 1
                continue
            except DefinitionError as exc:
                report(self, exc.issues)
                self.stderr.write(self.style.ERROR(f"skipped invalid definition: {path}"))
                skipped += 1
                continue
            except (OSError, ValueError) as exc:
                # Unreadable, truncated, conflict-marked or non-UTF-8 file
                # (JSONDecodeError and UnicodeDecodeError are ValueErrors).
                self.stderr.write(self.style.ERROR(f"skipped unreadable definition: {path}: {exc}"))
                skipped += 1
                continue
            except (DataError, IntegrityError) as exc:
                # A value the schema admits but the database refuses (or a
                # concurrent load).
                self.stderr.write(self.style.ERROR(f"skipped {path}: {exc}"))
                skipped += 1
                continue
            report(self, result.warnings)
            state = "created" if result.created else ("updated" if result.changed else "unchanged")
            self.stdout.write(f"{state}: {result.version} <- {path}")
        if skipped:
            raise CommandError(f"{skipped} of {len(files)} definition(s) skipped (see above)")
