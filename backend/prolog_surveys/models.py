"""PROlog data model.

Phase 1: survey identity, immutable versions, and read-only projections of
questions/options materialised on activation. Later phases add responses,
answers, consent, contacts, invitations and mappings.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

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


class SurveyVersion(models.Model):
    """Immutable snapshot of one instrument version (DEF-1, DEF-8)."""

    survey = models.ForeignKey(Survey, on_delete=models.PROTECT, related_name="versions")
    version = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16, choices=LifecycleStatus.choices, default=LifecycleStatus.DRAFT
    )
    schema_version = models.PositiveIntegerField(default=1)
    definition = models.JSONField(help_text="Normalised definition; the runner's contract.")
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
    def languages(self) -> list[str]:
        return list(self.definition.get("languages", []))

    @property
    def default_language(self) -> str:
        return self.definition["default_language"]


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
            null=True,
            blank=True,
            on_delete=models.PROTECT,
            related_name="prolog_survey_responses",
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
        indexes = [models.Index(fields=["survey_version", "status", "started_at"])]

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
        return self.survey_version.definition

    def answer_map(self) -> dict[str, dict]:
        return {a.question_key: a.value for a in self.answers.all()}


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

    @property
    def is_skipped(self) -> bool:
        return bool(self.value.get("skipped"))


class SurveyContact(models.Model):
    """Contact capture (CON-3). Deliberately has NO reference to a response."""

    survey_version = models.ForeignKey(
        SurveyVersion, on_delete=models.PROTECT, related_name="contacts"
    )
    email = models.EmailField()
    language = models.CharField(max_length=12, blank=True, default="")
    consent_text = models.TextField(help_text="The notice shown when the address was given.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"contact #{self.pk}"


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
