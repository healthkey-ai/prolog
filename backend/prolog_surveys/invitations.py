"""Invitations and repeat administration (RUN-5)."""

from __future__ import annotations

import calendar
import datetime as dt
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from django.core.mail import EmailMultiAlternatives, mailers
from django.db.models import Q
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


@dataclass(frozen=True)
class _Cycle:
    """What one survey administers today: the due date of the current cycle,
    the version it is bound to (None = whatever is active when answered) and
    whether the schedule repeats (a one-off is administered once, ever)."""

    survey: Survey
    invitations: list[SurveyInvitation]
    due_at: dt.date
    version: SurveyVersion | None
    repeats: bool


def _current_cycle(
    version: SurveyVersion, invitations: list[SurveyInvitation], today: dt.date
) -> _Cycle | None:
    survey = version.survey
    if not takes_invitations(version.definition):
        log.warning(
            "survey %s is anonymous; its %d active invitation(s) are not scheduled",
            survey.slug,
            len(invitations),
        )
        return None
    if reason := survey.closed_reason():
        # Outside the effective window the link would be refused (410), so no
        # administration is created; the cycle is not back-filled on reopening.
        log.info("survey %s is not scheduled: %s", survey.slug, reason)
        return None
    repeat = version.definition["participation"].get("repeat")
    current = current_due_date(repeat, today) if repeat else today
    if current is None:
        return None
    scheduled_version = None if (repeat or {}).get("use_current_version") else version
    return _Cycle(survey, invitations, current, scheduled_version, bool(repeat))


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

    cycles: list[_Cycle] = []
    for version in versions:
        survey_invitations = by_survey.get(version.survey_id, [])
        if not survey_invitations:
            continue
        try:
            cycle = _current_cycle(version, survey_invitations, today)
        except Exception:
            # One malformed schedule must not stop every other survey's mail.
            log.exception("could not schedule survey %s", version.survey.slug)
            continue
        if cycle is not None:
            cycles.append(cycle)
    if not cycles:
        return []

    # Only the administrations that would collide with today's cycle are read
    # back: the current due date per repeating survey, any at all for a one-off.
    scope = Q()
    for cycle in cycles:
        q = Q(invitation__survey_id=cycle.survey.id)
        if cycle.repeats:
            q &= Q(due_at=cycle.due_at)
        scope |= q
    done = set(SurveyAdministration.objects.filter(scope).values_list("invitation_id", flat=True))

    pending = [
        SurveyAdministration(
            invitation=invitation, survey_version=cycle.version, due_at=cycle.due_at
        )
        for cycle in cycles
        for invitation in cycle.invitations
        if invitation.id not in done
    ]
    return SurveyAdministration.objects.bulk_create(pending)


def send_pending() -> int:
    """Email every unsent administration whose invitation is active and has an address."""
    sent = 0
    pending = (
        SurveyAdministration.objects.filter(sent_at__isnull=True, invitation__active=True)
        .exclude(invitation__email="")
        .select_related("invitation__survey", "survey_version")
        .defer("survey_version__definition")
    )
    # Definitions are decoded (through cached_definition) only for the versions
    # that are actually sent, not for every active survey.
    active_versions = {
        v.survey_id: v
        for v in SurveyVersion.objects.filter(status=LifecycleStatus.ACTIVE).defer("definition")
    }
    skipped_anonymous: set[str] = set()
    mailer = mailers.default
    with mailer:  # one mail session for the whole batch
        for administration in pending:
            survey = administration.invitation.survey
            try:
                version = version_for(administration, active_versions)
                if version is None:
                    continue
                if not takes_invitations(version.cached_definition):
                    # The survey went anonymous after the administration was created:
                    # the link would be refused, so the email must not go out.
                    skipped_anonymous.add(survey.slug)
                    continue
                if reason := survey.closed_reason():
                    # Left unsent (not marked): it goes out if the survey reopens.
                    log.info("invitation for survey %s not sent (%s)", survey.slug, reason)
                    continue
                if not _send_one(mailer, administration, version):
                    # Left pending: the next run retries it.
                    log.warning(
                        "invitation for survey %s not sent (mailer reported 0 sent)", survey.slug
                    )
                    continue
            except Exception:
                log.exception(
                    "could not send administration %s of survey %s", administration.pk, survey.slug
                )
                continue
            sent += 1
    for slug in sorted(skipped_anonymous):
        log.warning("survey %s is anonymous; its pending invitation(s) are not sent", slug)
    return sent


def _send_one(mailer, administration: SurveyAdministration, version: SurveyVersion) -> bool:
    """Send one invitation; True when the mailer reports it sent (only then is it stamped)."""
    invitation = administration.invitation
    survey = invitation.survey
    definition = version.cached_definition
    default = definition["default_language"]
    lang = invitation.language or default
    title = pick(definition["title"], lang, default)
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
    if mailer.send_messages([message]) != 1:
        return False
    administration.sent_at = timezone.now()
    administration.save(update_fields=["sent_at"])
    return True


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
