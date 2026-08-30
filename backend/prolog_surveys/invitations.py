"""Invitations and repeat administration (RUN-5)."""

from __future__ import annotations

import calendar
import datetime as dt
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, mailers
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from . import conf
from .engine.localize import pick
from .models import LifecycleStatus, Survey, SurveyAdministration, SurveyInvitation, SurveyVersion

log = logging.getLogger(__name__)

# PostgreSQL advisory lock key held for the duration of a send_due_invitations
# run so two runs (cron plus a manual one, two schedulers) never overlap.
RUN_LOCK_KEY = 0x50524F4C  # "PROL"

# Chrome of the invitation email per language (the title is the survey's own
# translation). A host overriding the templates receives the same table as
# ``t`` plus ``language``. Regional variants fall back to the base language,
# unknown languages to English.
EMAIL_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "intro": "You are invited to complete:",
        "open": "Open your survey",
        "footer": "This link is personal to you. If you did not expect this email, "
        "you can ignore it.",
    },
    "es": {
        "intro": "Le invitamos a completar:",
        "open": "Abrir su cuestionario",
        "footer": "Este enlace es personal. Si no esperaba este correo, puede ignorarlo.",
    },
    "fr": {
        "intro": "Vous êtes invité(e) à remplir :",
        "open": "Ouvrir votre questionnaire",
        "footer": "Ce lien vous est personnel. Si vous n'attendiez pas ce courriel, "
        "vous pouvez l'ignorer.",
    },
    "pt": {
        "intro": "Convidamos você a preencher:",
        "open": "Abrir o seu questionário",
        "footer": "Este link é pessoal. Se não esperava este e-mail, pode ignorá-lo.",
    },
}

# Hosts an invitation link must never point at outside development.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def email_strings(lang: str) -> dict[str, str]:
    for candidate in (lang, lang.split("-")[0].split("_")[0], "en"):
        if candidate in EMAIL_STRINGS:
            return EMAIL_STRINGS[candidate]
    return EMAIL_STRINGS["en"]


def public_url_problem() -> str | None:
    """Why PROLOG_PUBLIC_URL cannot be emailed to participants, or None.

    The development default (localhost) is fine under DEBUG; a deployment
    that forgot the setting would otherwise mail unusable links and stamp the
    administrations sent, so they are never re-sent with the corrected URL.
    """
    url = conf.get("PROLOG_PUBLIC_URL")
    host = (urlsplit(url).hostname or "").lower() if url else ""
    if not host:
        return f"PROLOG_PUBLIC_URL is not an absolute URL: {url!r}"
    if not settings.DEBUG and host in _LOCAL_HOSTS:
        return f"PROLOG_PUBLIC_URL points at {host} ({url!r}); set the public origin"
    return None


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
    # Another run may have inserted some of these between the read of ``done``
    # and here; the conflicting rows are skipped rather than aborting the
    # statement. pks are client-generated, so the rows that landed are those
    # that carry them.
    SurveyAdministration.objects.bulk_create(pending, ignore_conflicts=True)
    return list(SurveyAdministration.objects.filter(pk__in=[a.pk for a in pending]))


def send_pending() -> int:
    """Email every unsent administration whose invitation is active and has an address."""
    if problem := public_url_problem():
        # Left pending, unstamped: the batch goes out once the URL is corrected.
        log.error("no invitation sent: %s", problem)
        return 0
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
                    # Scheduled version archived and nothing active: left pending.
                    log.info("invitation for survey %s not sent (no active version)", survey.slug)
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
            except Exception as exc:
                # The administration id is the participant's credential and a
                # mail server's message can carry the address: log neither.
                log.error(
                    "could not send invitation %s of survey %s: %s",
                    administration.invitation_id,
                    survey.slug,
                    type(exc).__name__,
                )
                log.debug("invitation %s send failure", administration.invitation_id, exc_info=True)
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
        "language": lang,
        "t": email_strings(lang),
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
