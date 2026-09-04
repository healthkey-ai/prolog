from django.core.management.base import BaseCommand, CommandError

from ...definitions.loader import ActivationError, DefinitionError, discover, load_file
from ._definitions import report


class Command(BaseCommand):
    help = (
        "Load survey definition files (or directories) as draft versions; idempotent. "
        "Use --activate to make each loaded version the active one."
    )

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Definition files or directories")
        parser.add_argument("--activate", action="store_true")
        parser.add_argument(
            "--discard-responses",
            action="store_true",
            help=(
                "Re-load over a version that has responses, deleting them. They are the "
                "test data from trying the instrument out; a published version refuses "
                "this outright."
            ),
        )
        parser.add_argument(
            "--allow-unreviewed",
            action="store_true",
            help="Activate even if some translations are 'machine' (local/staging review only).",
        )

    def handle(self, *args, **options):
        files = discover(options["paths"])
        if not files:
            raise CommandError("no definition files found")
        for path in files:
            try:
                result = load_file(
                    path,
                    activate=options["activate"],
                    allow_unreviewed=options["allow_unreviewed"],
                    discard_responses=options["discard_responses"],
                )
            except DefinitionError as exc:
                report(self, exc.issues)
                raise CommandError(f"invalid definition: {path}") from exc
            except ActivationError as exc:
                raise CommandError(f"{path}: {exc}") from exc
            report(self, result.warnings)
            state = "created" if result.created else ("updated" if result.changed else "unchanged")
            suffix = ", activated" if result.activated else ""
            self.stdout.write(self.style.SUCCESS(f"{state}{suffix}: {result.version} <- {path}"))
