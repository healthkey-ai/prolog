"""Withdraw a consent given with an address (CON-9), or the address itself.

A withdrawal is recorded, never erased: that consent was given, and until when,
is what a controller has to be able to show. The address itself may be erased
(``--erase``) when the person wants off the list altogether.

Contact capture keeps the address on the contact row, so ``--email`` finds it
there; identity capture keeps it in the host's account, so the host supplies
the participant (``--participant``) and the consents are the rows against
that participant's responses.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ...models import Survey, SurveyCaptureConsent, SurveyContact, SurveyResponse


class Command(BaseCommand):
    help = "Record the withdrawal of consents given with an address; --erase removes a captured address."

    def add_arguments(self, parser):
        parser.add_argument("slug")
        who = parser.add_mutually_exclusive_group(required=True)
        who.add_argument("--email", help="Contact capture: the address on the contact row")
        who.add_argument(
            "--participant",
            help="Identity capture: the participant the host resolved the address to",
        )
        parser.add_argument(
            "--consent",
            action="append",
            default=[],
            metavar="KEY",
            help="Consent key to withdraw; repeatable. Default: every consent given.",
        )
        parser.add_argument(
            "--erase",
            action="store_true",
            help="Contact capture only: delete the contact row(s) — the address goes, consents with it.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            survey = Survey.objects.get(slug=options["slug"])
        except Survey.DoesNotExist as exc:
            raise CommandError(f"unknown survey '{options['slug']}'") from exc
        keys = set(options["consent"])
        if options["email"]:
            self._contacts(survey, options["email"], keys, options["erase"], options["dry_run"])
        else:
            if options["erase"]:
                raise CommandError("--erase applies to contact capture; an identity is the host's")
            self._captures(survey, options["participant"], keys, options["dry_run"])

    def _contacts(self, survey, email: str, keys: set[str], erase: bool, dry_run: bool) -> None:
        rows = SurveyContact.objects.filter(survey_version__survey=survey, email__iexact=email)
        if not rows.exists():
            raise CommandError("no contact row holds that address for this survey")
        today = timezone.localdate().isoformat()
        if erase:
            n = rows.count()
            if not dry_run:
                rows.delete()
            self.stdout.write(f"{'would erase' if dry_run else 'erased'} {n} contact row(s)")
            return
        withdrawn = 0
        with transaction.atomic():
            for row in rows.select_for_update():
                changed = False
                for entry in row.consents:
                    if (not keys or entry["key"] in keys) and "withdrawn_on" not in entry:
                        entry["withdrawn_on"] = today
                        changed, withdrawn = True, withdrawn + 1
                if changed and not dry_run:
                    row.save(update_fields=["consents"])
        self._report(withdrawn, keys, dry_run)

    def _captures(self, survey, participant: str, keys: set[str], dry_run: bool) -> None:
        if not any(f.name == "participant" for f in SurveyResponse._meta.get_fields()):
            raise CommandError("--participant needs the integrated profile")
        rows = SurveyCaptureConsent.objects.filter(
            response__survey_version__survey=survey,
            response__participant_id=participant,
            withdrawn_at__isnull=True,
        )
        if keys:
            rows = rows.filter(key__in=keys)
        n = rows.count() if dry_run else rows.update(withdrawn_at=timezone.now())
        self._report(n, keys, dry_run)

    def _report(self, n: int, keys: set[str], dry_run: bool) -> None:
        what = ", ".join(sorted(keys)) if keys else "every consent"
        self.stdout.write(f"{'would withdraw' if dry_run else 'withdrew'} {n} consent(s) ({what})")
