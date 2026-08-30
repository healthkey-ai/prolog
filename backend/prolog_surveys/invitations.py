"""Invitations and repeat administration (RUN-5)."""

from __future__ import annotations

import calendar
import datetime as dt
from collections.abc import Iterator
from typing import Any

from django.core.mail import EmailMultiAlternatives, mailers
from django.template.loader import render_to_string
from django.utils import timezone

from . import conf
from .engine.localize import pick
from .models import LifecycleStatus, Survey, SurveyAdministration


def add_months(day: dt.date, months: int) -> dt.date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last))


def due_dates(repeat: dict[str, Any], until: dt.date) -> Iterator[dt.date]:
    """Administration dates from start_date every N weeks/months, up to ``until``/end_date."""
    start = dt.date.fromisoformat(repeat["start_date"])
    end = dt.date.fromisoformat(repeat["end_date"]) if repeat.get("end_date") else None
    n = 0
    while True:
        day = (
            start + dt.timedelta(weeks=repeat["every"] * n)
            if repeat["unit"] == "weeks"
            else add_months(start, repeat["every"] * n)
        )
        if day > until or (end and day > end):
            return
        yield day
        n += 1


def invitation_link(survey: Survey, administration: SurveyAdministration) -> str:
    return f"{conf.get('PROLOG_PUBLIC_URL').rstrip('/')}/s/{survey.slug}?invite={administration.id}"


def schedule_due(now: dt.date | None = None) -> list[SurveyAdministration]:
    """Create administrations that are due and not yet created; returns the new ones."""
    today = now or timezone.now().date()
    created: list[SurveyAdministration] = []
    for survey in Survey.objects.all():
        version = survey.active_version
        if version is None:
            continue
        repeat = version.definition["participation"].get("repeat")
        invitations = list(survey.invitations.filter(active=True))
        if not invitations:
            continue
        dates = list(due_dates(repeat, today)) if repeat else [today]
        scheduled_version = None if (repeat or {}).get("use_current_version") else version
        for invitation in invitations:
            existing = set(invitation.administrations.values_list("due_at", flat=True))
            for day in dates:
                if day in existing:
                    continue
                if not repeat and existing:
                    continue  # one-off surveys are administered once
                created.append(
                    SurveyAdministration.objects.create(
                        invitation=invitation, survey_version=scheduled_version, due_at=day
                    )
                )
    return created


def send_pending() -> int:
    """Email every unsent administration whose invitation is active and has an address."""
    sent = 0
    pending = (
        SurveyAdministration.objects.filter(sent_at__isnull=True, invitation__active=True)
        .exclude(invitation__email="")
        .select_related("invitation__survey", "survey_version")
    )
    mailer = mailers.default
    with mailer:  # one mail session for the whole batch
        for administration in pending:
            if _send_one(mailer, administration):
                sent += 1
    return sent


def _send_one(mailer, administration: SurveyAdministration) -> bool:
    invitation = administration.invitation
    survey = invitation.survey
    version = version_for(administration)
    if version is None:
        return False
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
    return True


def version_for(administration: SurveyAdministration):
    """Version a response to this administration must use: the scheduled one
    while it is active, otherwise whatever is active now."""
    scheduled = administration.survey_version
    if scheduled is not None and scheduled.status == LifecycleStatus.ACTIVE:
        return scheduled
    return administration.invitation.survey.active_version
