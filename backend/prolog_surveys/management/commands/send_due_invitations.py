from django.core.management.base import BaseCommand
from django.db import connection

from ...invitations import RUN_LOCK_KEY, schedule_due, send_pending


class Command(BaseCommand):
    help = "Create due survey administrations (repeat schedules) and email their invitation links. Run daily."

    def handle(self, *args, **options):
        # One run at a time (cron plus a manual run, two schedulers): the second
        # would otherwise compute the same batch and email participants twice.
        # A session-level advisory lock outlives no connection, so a crashed
        # run never leaves it held.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [RUN_LOCK_KEY])
            if not cursor.fetchone()[0]:
                self.stdout.write("send_due_invitations is already running; nothing done")
                return
        try:
            created = schedule_due()
            sent = send_pending()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [RUN_LOCK_KEY])
        self.stdout.write(f"created {len(created)} administration(s), sent {sent} invitation(s)")
