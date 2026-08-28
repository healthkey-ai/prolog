"""Initial data model. Generate migrations inside PRomop once installed there."""
import uuid
from django.db import models


class Survey(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    class IdentityCapturePlacement(models.TextChoices):
        NONE = "none", "No identity capture"
        START = "start", "At the start of the survey"
        END = "end", "At the end of the survey"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    allow_anonymous_participation = models.BooleanField(default=False)
    identity_capture_placement = models.CharField(
        max_length=8,
        choices=IdentityCapturePlacement.choices,
        default=IdentityCapturePlacement.NONE,
        help_text=(
            "Optional, consented email step for anonymous respondents. The email is "
            "sent to PRomop's patient-record service and is never a survey answer."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SurveyVersion(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField()
    language = models.CharField(max_length=12, default="en")
    schema = models.JSONField(default=dict, help_text="Frozen pages, questions, options, and rules.")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["survey", "number"], name="prolog_survey_version_unique")]


class SurveyResponse(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey_version = models.ForeignKey(SurveyVersion, on_delete=models.PROTECT, related_name="responses")
    person = models.ForeignKey("omop_core.Person", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="prolog_survey_responses")
    identity_linked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When an optional identity-capture action created and linked a PRomop patient record.",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    language = models.CharField(max_length=12)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)


class SurveyAnswer(models.Model):
    """Original answer is retained independently of any optional OMOP mapping."""
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name="answers")
    question_key = models.CharField(max_length=128)
    original_value = models.JSONField(help_text="Unchanged submitted answer, including selected options/text.")
    canonical_value = models.JSONField(help_text="Typed value usable for queries and optional mappings.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["response", "question_key"], name="prolog_response_question_unique")]


class ConceptMapping(models.Model):
    """An optional, approved derivation; it never replaces SurveyAnswer."""
    class TargetTable(models.TextChoices):
        OBSERVATION = "observation", "Observation"
        NOTE = "note", "Note"
        NOTE_NLP = "note_nlp", "Note NLP"

    survey_version = models.ForeignKey(SurveyVersion, on_delete=models.PROTECT, related_name="mappings")
    source_question_keys = models.JSONField(default=list)
    target_table = models.CharField(max_length=32, choices=TargetTable.choices)
    expression = models.JSONField(default=dict)
    rationale = models.TextField()
    approved_at = models.DateTimeField(null=True, blank=True)
