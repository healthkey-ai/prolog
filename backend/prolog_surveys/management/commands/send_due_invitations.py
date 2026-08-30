from django.core.management.base import BaseCommand

from ...invitations import schedule_due, send_pending


class Command(BaseCommand):
    help = "Create due survey administrations (repeat schedules) and email their invitation links. Run daily."

    def handle(self, *args, **options):
        created = schedule_due()
        sent = send_pending()
        self.stdout.write(f"created {len(created)} administration(s), sent {sent} invitation(s)")
