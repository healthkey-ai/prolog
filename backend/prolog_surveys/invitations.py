"""Invitations and repeat administration (RUN-5)."""

from __future__ import annotations

import calendar
import datetime as dt
import logging
from collections.abc import Iterator
from typing import Any

from django.core.mail import EmailMultiAlternatives, mailers
from django.template.loader import render_to_string
from django.utils import timezone

from . import conf
from .engine.localize import pick
from .models import LifecycleStatus, Survey, SurveyAdministration, SurveyInvitation, SurveyVersion

log = logging.getLogger(__name__)


def add_months(day: dt.date, months: int) -> dt.date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last))


def takes_invitations(definition: dict[str, Any]) -> bool:
    """Whether a survey may be administered by invitation.

    An invitation joins an email address (or participant) to the answers, so
    an anonymous survey takes none (CON-3); every path that links a token to a
    response or emails one checks here.
    """
    return not definition["participation"]["anonymous"]


def _due_date(repeat: dict[str, Any], n: int) -> dt.date:
    start = dt.date.fromisoformat(repeat["start_date"])
    if repeat["unit"] == "weeks":
        return start + dt.timedelta(weeks=repeat["every"] * n)
    return add_months(start, repeat["every"] * n)


def due_dates(repeat: dict[str, Any], until: dt.date) -> Iterator[dt.date]:
    """Administration dates from start_date every N weeks/months, up to ``until``/end_date."""
    end = dt.date.fromisoformat(repeat["end_date"]) if repeat.get("end_date") else None
    n = 0
    while True:
        day = _due_date(repeat, n)
        if day > until or (end and day > end):
            return
        yield day
        n += 1


def current_due_date(repeat: dict[str, Any], today: dt.date) -> dt.date | None:
    """Due date of the cycle ``today`` falls in: the latest date on or before
    today whose next cycle has not started. None before the first cycle, and
    once the cycle after ``end_date`` would have begun (the schedule is over).
    """
    n = -1
    for _ in due_dates(repeat, today):
        n += 1
    if n < 0 or _due_date(repeat, n + 1) <= today:
        return None
    return _due_date(repeat, n)


def invitation_link(survey: Survey, administration: SurveyAdministration) -> str:
    return f"{conf.get('PROLOG_PUBLIC_URL').rstrip('/')}/s/{survey.slug}?invite={administration.id}"


def schedule_due(now: dt.date | None = None) -> list[SurveyAdministration]:
    """Create the administrations that are due today and do not exist yet.

    Only the *current* cycle is ever created: an invitation added mid-schedule
    (or a scheduler that was down for a while) gets one link, never a backlog
    of past cycles' emails. A one-off survey is administered once.
    """
    today = now or timezone.localdate()
    versions = list(
        SurveyVersion.objects.filter(status=LifecycleStatus.ACTIVE).select_related("survey")
    )
    invitations = SurveyInvitation.objects.filter(
        active=True, survey__in=[v.survey_id for v in versions]
    )
    by_survey: dict[Any, list[SurveyInvitation]] = {}
    for invitation in invitations:
        by_survey.setdefault(invitation.survey_id, []).append(invitation)
    existing: dict[Any, set[dt.date]] = {}
    for invitation_id, due_at in SurveyAdministration.objects.filter(
        invitation__in=invitations
    ).values_list("invitation_id", "due_at"):
        existing.setdefault(invitation_id, set()).add(due_at)

    pending: list[SurveyAdministration] = []
    for version in versions:
        survey = version.survey
        survey_invitations = by_survey.get(survey.id, [])
        if not survey_invitations:
            continue
        if not takes_invitations(version.definition):
            log.warning(
                "survey %s is anonymous; its %d active invitation(s) are not scheduled",
                survey.slug,
                len(survey_invitations),
            )
            continue
        repeat = version.definition["participation"].get("repeat")
        current = current_due_date(repeat, today) if repeat else today
        if current is None:
            continue
        scheduled_version = None if (repeat or {}).get("use_current_version") else version
        for invitation in survey_invitations:
            done = existing.get(invitation.id, set())
            if current in done or (not repeat and done):
                continue
            pending.append(
                SurveyAdministration(
                    invitation=invitation, survey_version=scheduled_version, due_at=current
                )
            )
    return SurveyAdministration.objects.bulk_create(pending)


def send_pending() -> int:
    """Email every unsent administration whose invitation is active and has an address."""
    sent = 0
    pending = (
        SurveyAdministration.objects.filter(sent_at__isnull=True, invitation__active=True)
        .exclude(invitation__email="")
        .select_related("invitation__survey", "survey_version")
    )
    active_versions = {
        v.survey_id: v for v in SurveyVersion.objects.filter(status=LifecycleStatus.ACTIVE)
    }
    skipped_anonymous: set[str] = set()
    mailer = mailers.default
    with mailer:  # one mail session for the whole batch
        for administration in pending:
            version = version_for(administration, active_versions)
            if version is None:
                continue
            if not takes_invitations(version.definition):
                # The survey went anonymous after the administration was created:
                # the link would be refused, so the email must not go out.
                skipped_anonymous.add(administration.invitation.survey.slug)
                continue
            _send_one(mailer, administration, version)
            sent += 1
    for slug in sorted(skipped_anonymous):
        log.warning("survey %s is anonymous; its pending invitation(s) are not sent", slug)
    return sent


def _send_one(mailer, administration: SurveyAdministration, version: SurveyVersion) -> None:
    invitation = administration.invitation
    survey = invitation.survey
    lang = invitation.language or version.default_language
    title = pick(version.definition["title"], lang, version.default_language)
    context = {
        "title": title,
        "link": invitation_link(survey, administration),
        "due": administration.due_at,
    }
    message = EmailMultiAlternatives(
        subject=render_to_string("prolog_surveys/email/invitation_subject.txt", context).strip(),
        body=render_to_string("prolog_surveys/email/invitation.txt", context),
        from_email=conf.get("PROLOG_EMAIL_FROM"),
        to=[invitation.email],
    )
    message.attach_alternative(
        render_to_string("prolog_surveys/email/invitation.html", context), "text/html"
    )
    mailer.send_messages([message])
    administration.sent_at = timezone.now()
    administration.save(update_fields=["sent_at"])


def version_for(
    administration: SurveyAdministration,
    active_versions: dict[Any, SurveyVersion] | None = None,
) -> SurveyVersion | None:
    """Version a response to this administration must use: the scheduled one
    while it is active, otherwise whatever is active now.

    ``active_versions`` (survey id -> active version) lets a batch avoid one
    query per administration.
    """
    scheduled = administration.survey_version
    if scheduled is not None and scheduled.status == LifecycleStatus.ACTIVE:
        return scheduled
    survey = administration.invitation.survey
    if active_versions is not None:
        return active_versions.get(survey.id)
    return survey.active_version
