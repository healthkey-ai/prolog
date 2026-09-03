from django.core.management.base import BaseCommand

from ...definitions.loader import publish_version
from ._versions import resolve_version


class Command(BaseCommand):
    help = (
        "Freeze a version's content for good. Activation decides which version is served; "
        "publishing decides its content is final — after it, a re-load is refused and the "
        "responses against it can no longer be discarded."
    )

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--survey-version", default=None, help="Defaults to the active version")

    def handle(self, *args, **options):
        version = resolve_version(options["slug"], options["survey_version"])
        if version.is_published:
            self.stdout.write(
                f"already published on {version.published_at:%Y-%m-%d %H:%M}: {version}"
            )
            return
        total = version.responses.count()
        publish_version(version)
        self.stdout.write(
            self.style.SUCCESS(
                f"published: {version}. Its content is frozen"
                + (f"; its {total} response(s) are answers now, not test data." if total else ".")
            )
        )
