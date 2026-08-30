from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ... import conf
from ...models import ResponseStatus, SurveyResponse

# Responses deleted per transaction: each cascades to its answers, so a
# backlog of thousands would otherwise hold one long transaction (and its
# locks) while the runner keeps writing.
BATCH_SIZE = 1000


class Command(BaseCommand):
    help = "Delete in-progress responses not updated for PROLOG_ABANDONED_RESPONSE_DAYS (retention, NFR-1)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = conf.get("PROLOG_ABANDONED_RESPONSE_DAYS")
        cutoff = timezone.now() - timedelta(days=days)
        qs = SurveyResponse.objects.filter(status=ResponseStatus.IN_PROGRESS, updated_at__lt=cutoff)
        if options["dry_run"]:
            n = qs.count()
            self.stdout.write(f"would delete {n} abandoned response(s) older than {days} days")
            return
        n = 0
        while batch := list(qs.values_list("pk", flat=True)[:BATCH_SIZE]):
            SurveyResponse.objects.filter(pk__in=batch).delete()
            n += len(batch)
        self.stdout.write(f"deleted {n} abandoned response(s) older than {days} days")
