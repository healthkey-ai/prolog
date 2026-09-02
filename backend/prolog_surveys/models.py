"""PROlog data model.

Phase 1: survey identity, immutable versions, and read-only projections of
questions/options materialised on activation. Later phases add responses,
answers, consent, contacts, invitations and mappings.
"""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .engine.localize import localize, resolve_language

PARTICIPANT_MODEL = getattr(settings, "PROLOG_PARTICIPANT_MODEL", None)


class LifecycleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class Survey(models.Model):
    """Stable identity of a survey across versions (DEF-3)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=255, help_text="Title in the default language.")
    theme_code = models.SlugField(max_length=64, blank=True, default="")
    allow_anonymous_participation = models.BooleanField(default=False)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.slug

    @property
    def active_version(self) -> SurveyVersion | None:
        return self.versions.filter(status=LifecycleStatus.ACTIVE).first()

    def closed_reason(self) -> str | None:
        """Why the survey is outside its effective window today, or None if open.

        ``effective_from``/``effective_to`` are calendar dates in the
        deployment's TIME_ZONE, so compare with the local date, not the UTC one.
        """
        today = timezone.localdate()
        if self.effective_from and self.effective_from > today:
            return "survey is not yet open"
        if self.effective_to and self.effective_to < today:
            return "survey has closed"
        return None


class SurveyVersion(models.Model):
    """Immutable snapshot of one instrument version (DEF-1, DEF-8)."""

    survey = models.ForeignKey(Survey, on_delete=models.PROTECT, related_name="versions")
    version = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16, choices=LifecycleStatus.choices, default=LifecycleStatus.DRAFT
    )
    schema_version = models.PositiveIntegerField(default=1)
    definition = models.JSONField(help_text="Normalised definition; the runner's contract.")
    # Identifies the *source* document (normalize.source_checksum), so an unchanged
    # file re-loads after a normaliser change; the help_text predates that and is
    # left alone because changing it would need a migration.
    checksum = models.CharField(max_length=64, help_text="SHA-256 of the normalised definition.")
    source = models.CharField(
        max_length=512, blank=True, default="", help_text="File it was loaded from."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["survey", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["survey", "version"], name="prolog_version_unique"),
            models.UniqueConstraint(
                fields=["survey"],
                condition=Q(status="active"),
                name="prolog_one_active_version_per_survey",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.survey.slug}@{self.version} ({self.status})"

    @property
    def is_mutable(self) -> bool:
        return self.status == LifecycleStatus.DRAFT

    @property
    def default_language(self) -> str:
        return self.definition["default_language"]

    @property
    def cached_definition(self) -> dict:
        """The definition, decoded once per process.

        Published versions are immutable and a draft's checksum changes with its
        body, so (pk, checksum) can never serve a stale document. Runner views
        defer the JSON column and read it through here; the returned dict is
        shared and must not be mutated.
        """
        # ``self.definition`` is a refresh query when the column was deferred.
        return _cached(_definition_cache, (self.pk, self.checksum), lambda: self.definition)

    def localized(self, lang: str) -> dict:
        """``cached_definition`` localised for ``lang`` (resolved to an offered
        language), built once per process per (version, language). The
        returned dict is shared and must not be mutated: copy before adding
        per-request keys."""
        definition = self.cached_definition
        lang = resolve_language(definition, lang)
        return _cached(
            _localized_cache,
            (self.pk, self.checksum, lang),
            lambda: localize(definition, lang),
        )


_CACHE_SIZE = 64
_definition_cache: OrderedDict[tuple, dict] = OrderedDict()
_localized_cache: OrderedDict[tuple, dict] = OrderedDict()
_cache_lock = threading.Lock()


def _cached(cache: OrderedDict[tuple, dict], key: tuple, compute) -> dict:
    """Small per-process LRU: published versions are immutable and a draft's
    checksum changes with its body, so a (pk, checksum) key never serves a
    stale document."""
    with _cache_lock:
        doc = cache.get(key)
        if doc is not None:
            cache.move_to_end(key)
            return doc
    doc = compute()
    with _cache_lock:
        cache[key] = doc
        while len(cache) > _CACHE_SIZE:
            cache.popitem(last=False)
    return doc


class SurveyQuestion(models.Model):
    """Read-only projection of a question, materialised on activation.

    Gives mappings, analytics and exports stable foreign keys; the JSON
    definition on the version stays authoritative.
    """

    survey_version = models.ForeignKey(
        SurveyVersion, on_delete=models.CASCADE, related_name="questions"
    )
    key = models.CharField(max_length=128)
    section_key = models.CharField(max_length=128)
    type = models.CharField(max_length=16)
    order = models.PositiveIntegerField(help_text="Presentation index across the whole instrument.")
    text = models.TextField(help_text="Question text in the default language.")
    required = models.BooleanField(default=True)

    class Meta:
        ordering = ["survey_version", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["survey_version", "key"], name="prolog_question_key_unique"
            )
        ]

    def __str__(self) -> str:
        return self.key


class SurveyOption(models.Model):
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name="options")
    key = models.CharField(max_length=128)
    order = models.PositiveIntegerField()
    label = models.TextField(help_text="Label in the default language.")
    exclusive = models.BooleanField(default=False)
    free_text = models.BooleanField(default=False)

    class Meta:
        ordering = ["question", "order"]
        constraints = [
            models.UniqueConstraint(fields=["question", "key"], name="prolog_option_key_unique")
        ]

    def __str__(self) -> str:
        return f"{self.question.key}:{self.key}"


class ResponseStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "In progress"
    SUBMITTED = "submitted", "Submitted"


class SurveyResponse(models.Model):
    """One participant attempt (RUN-2, RUN-4). The UUID is the capability token."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey_version = models.ForeignKey(
        SurveyVersion, on_delete=models.PROTECT, related_name="responses"
    )
    language = models.CharField(max_length=12)
    status = models.CharField(
        max_length=16, choices=ResponseStatus.choices, default=ResponseStatus.IN_PROGRESS
    )
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_question_key = models.CharField(max_length=128, blank=True, default="")
    user_agent_hash = models.CharField(
        max_length=64, blank=True, default="", help_text="Salted hash; never the raw user agent."
    )
    # Integrated profile only (DEP-2): the field exists when PROLOG_PARTICIPANT_MODEL
    # is set; the host project generates the migration that adds it.
    if PARTICIPANT_MODEL:
        participant = models.ForeignKey(
            PARTICIPANT_MODEL,
            on_delete=models.PROTECT,
            related_name="prolog_survey_responses",
            help_text="Never null (DEP-2/RUN-2): where nobody is signed in the host mints one.",
        )
    identity_linked_at = models.DateTimeField(
        null=True, blank=True, help_text="When identity capture linked this response (CON-4)."
    )
    administration = models.OneToOneField(
        "SurveyAdministration",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="response",
        help_text="The invitation occurrence this response answers (RUN-5).",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["survey_version", "status", "started_at"]),
            # ``purge_abandoned_responses`` scans in-progress rows by age.
            models.Index(
                fields=["updated_at"],
                condition=Q(status="in_progress"),
                name="prolog_response_inprogress_upd",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.id} ({self.status})"

    @property
    def participant_id_or_none(self):
        return getattr(self, "participant_id", None)

    @property
    def is_submitted(self) -> bool:
        return self.status == ResponseStatus.SUBMITTED

    @property
    def definition(self) -> dict:
        return self.survey_version.cached_definition

    def answer_map(self) -> dict[str, dict]:
        return {a.question_key: a.value for a in self.answers.all()}


class MintedParticipant(models.Model):
    """A participant record PROlog created for a respondent who was not signed in.

    The host's participant table is its own — in PRomop, `Person` in the OMOP
    CDM — and a row minted for a survey is indistinguishable there from a
    patient. This is how the host can tell: a participant listed here with
    `identified_at` unset is a respondent nobody has claimed, and belongs in no
    count of patients. `identified_at` is stamped when the same record gains an
    account (CON-4), after which it is an ordinary participant and the row is
    only history.

    The app owns this table; it never adds a column to the host's (DEP-7).
    """

    if PARTICIPANT_MODEL:
        participant = models.OneToOneField(
            PARTICIPANT_MODEL,
            on_delete=models.CASCADE,
            related_name="prolog_minted",
        )
    created_at = models.DateTimeField(auto_now_add=True)
    identified_at = models.DateTimeField(
        null=True, blank=True, help_text="When this participant gained an account (CON-4)."
    )

    class Meta:
        indexes = [models.Index(fields=["identified_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"minted participant {getattr(self, 'participant_id', None)}"


class ParticipantMergeCandidate(models.Model):
    """Two participant records a human may need to reconcile (CON-4, decision 7).

    Written when a respondent gives an address that already belongs to a
    different participant. Nothing is attached: the response stays with the
    participant it was minted for, because joining two patient records is a
    clinical-safety decision and a confirmed address is not proof that two
    records are the same person.

    It holds the two ids and nothing else — never the address, which PROlog does
    not store (CON-4). The host has the address already; this says which pair to
    look at.
    """

    if PARTICIPANT_MODEL:
        minted = models.ForeignKey(
            PARTICIPANT_MODEL,
            on_delete=models.CASCADE,
            related_name="prolog_merge_candidates",
            help_text="The participant the response is bound to.",
        )
        existing = models.ForeignKey(
            PARTICIPANT_MODEL,
            on_delete=models.CASCADE,
            related_name="prolog_merge_claims",
            help_text="The participant the address already belongs to.",
        )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(
        null=True, blank=True, help_text="When a human settled this pair."
    )

    class Meta:
        indexes = [models.Index(fields=["resolved_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"merge candidate {getattr(self, 'minted_id', None)}/{getattr(self, 'existing_id', None)}"


class SurveyAnswer(models.Model):
    """Authoritative raw answer for one question (Q-1…Q-12)."""

    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name="answers")
    question_key = models.CharField(max_length=128)
    value = models.JSONField(help_text="Canonical value shape for the question type.")
    option_keys = models.JSONField(
        default=list,
        blank=True,
        help_text="Selected option keys (single/multi/ranking) for querying.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["response", "question_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["response", "question_key"], name="prolog_answer_unique"
            )
        ]
        indexes = [models.Index(fields=["question_key"])]

    def __str__(self) -> str:
        return f"{self.response_id}:{self.question_key}"


class SurveyContact(models.Model):
    """Contact capture (CON-3). Deliberately has NO reference to a response.

    Nothing on the row may act as a join key to the response either: the pk is
    random (a sequence would order contacts like the responses' answer rows)
    and the capture time is kept to the day (a timestamp would pair each
    contact with the ``{provided: true}`` marker written in the same request).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey_version = models.ForeignKey(
        SurveyVersion, on_delete=models.PROTECT, related_name="contacts"
    )
    email = models.EmailField()
    language = models.CharField(max_length=12, blank=True, default="")
    consent_text = models.TextField(help_text="The notice shown when the address was given.")
    captured_on = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-captured_on"]

    def __str__(self) -> str:
        return f"contact {self.pk}"


class SurveyConsent(models.Model):
    """Versioned consent attestation (CON-1); never an answer."""

    response = models.OneToOneField(
        SurveyResponse, on_delete=models.CASCADE, related_name="consent"
    )
    consent_version = models.CharField(max_length=64)
    text_hash = models.CharField(max_length=64, help_text="SHA-256 of the notice shown.")
    language = models.CharField(max_length=12)
    agreed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"consent {self.consent_version} for {self.response_id}"


class SurveyInvitation(models.Model):
    """An invited participant of a non-anonymous survey (RUN-5).

    Identified by a participant record (integrated profile) and/or an email
    address; the invitation token in the link is the credential when no
    account is involved.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField(blank=True, default="")
    if PARTICIPANT_MODEL:
        participant = models.ForeignKey(
            PARTICIPANT_MODEL,
            null=True,
            blank=True,
            on_delete=models.CASCADE,
            related_name="prolog_survey_invitations",
        )
    language = models.CharField(max_length=12, blank=True, default="")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["survey", "created_at"]

    def __str__(self) -> str:
        return f"invitation {self.id} to {self.survey.slug}"

    def clean(self) -> None:
        # An invitation joins an address to the answers, which an anonymous
        # survey promises not to do (CON-3); the admin form reports this.
        if self.survey_id and self.survey.allow_anonymous_participation:
            raise ValidationError({"survey": "an anonymous survey takes no invitations"})


class SurveyAdministration(models.Model):
    """One occurrence of a survey being offered to an invited participant (RUN-5)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invitation = models.ForeignKey(
        SurveyInvitation, on_delete=models.CASCADE, related_name="administrations"
    )
    survey_version = models.ForeignKey(
        SurveyVersion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="administrations",
        help_text="Scheduled version; null = the version active when the participant starts.",
    )
    due_at = models.DateField()
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["invitation", "due_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["invitation", "due_at"], name="prolog_administration_unique"
            )
        ]

    def __str__(self) -> str:
        return f"administration {self.due_at} of {self.invitation_id}"
