"""Invitations and repeat administration (RUN-5)."""

from __future__ import annotations

import calendar
import datetime as dt
from collections.abc import Iterator
from typing import Any

from django.core.mail import send_mail
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
    """Email every unsent administration whose invitation has an address."""
    sent = 0
    for administration in SurveyAdministration.objects.filter(sent_at__isnull=True).select_related(
        "invitation__survey"
    ):
        invitation = administration.invitation
        if not invitation.email:
            continue
        survey = invitation.survey
        version = administration.survey_version or survey.active_version
        if version is None:
            continue
        lang = invitation.language or version.default_language
        title = pick(version.definition["title"], lang, version.default_language)
        context = {
            "title": title,
            "link": invitation_link(survey, administration),
            "due": administration.due_at,
        }
        send_mail(
            subject=render_to_string(
                "prolog_surveys/email/invitation_subject.txt", context
            ).strip(),
            message=render_to_string("prolog_surveys/email/invitation.txt", context),
            from_email=conf.get("PROLOG_EMAIL_FROM"),
            recipient_list=[invitation.email],
            html_message=render_to_string("prolog_surveys/email/invitation.html", context),
        )
        administration.sent_at = timezone.now()
        administration.save(update_fields=["sent_at"])
        sent += 1
    return sent


def version_for(administration: SurveyAdministration):
    """Version a response to this administration must use."""
    if (
        administration.survey_version
        and administration.survey_version.status != LifecycleStatus.ARCHIVED
    ):
        return administration.survey_version
    return administration.invitation.survey.active_version
