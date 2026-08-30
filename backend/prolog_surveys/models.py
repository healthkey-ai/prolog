"""PROlog data model.

Phase 1: survey identity, immutable versions, and read-only projections of
questions/options materialised on activation. Later phases add responses,
answers, consent, contacts, invitations and mappings.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q


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
