from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ... import conf
from ...models import ResponseStatus, SurveyResponse


class Command(BaseCommand):
    help = "Delete in-progress responses not updated for PROLOG_ABANDONED_RESPONSE_DAYS (retention, NFR-1)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        days = options["days"] or conf.get("PROLOG_ABANDONED_RESPONSE_DAYS")
        cutoff = timezone.now() - timedelta(days=days)
        qs = SurveyResponse.objects.filter(status=ResponseStatus.IN_PROGRESS, updated_at__lt=cutoff)
        n = qs.count()
        if options["dry_run"]:
            self.stdout.write(f"would delete {n} abandoned response(s) older than {days} days")
            return
        qs.delete()
        self.stdout.write(f"deleted {n} abandoned response(s) older than {days} days")
