from django.contrib import admin
from django.db.models import Count, OuterRef, Q, Subquery

from .models import (
    LifecycleStatus,
    Survey,
    SurveyAdministration,
    SurveyAnswer,
    SurveyConsent,
    SurveyContact,
    SurveyInvitation,
    SurveyOption,
    SurveyQuestion,
    SurveyResponse,
    SurveyVersion,
)


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class VersionInline(admin.TabularInline):
    model = SurveyVersion
    fields = ("version", "status", "schema_version", "published_at", "archived_at", "source")
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = (
        "slug",
        "title",
        "theme_code",
        "allow_anonymous_participation",
        "active",
        "responses",
    )
    search_fields = ("slug", "title")
    # Loader-owned: the loader finds a survey by ``slug`` (changing it here
    # would orphan the survey and every link sent) and rewrites ``title``,
    # ``theme_code`` and ``allow_anonymous_participation`` from the definition
    # on every load, so edits here would only drift from the instrument until
    # the next load reverts them. Only the effective window is admin-owned.
    loader_fields = ("slug", "title", "theme_code", "allow_anonymous_participation")
    readonly_fields = ("allow_anonymous_participation",)
    inlines = [VersionInline]

    def get_readonly_fields(self, request, obj=None):
        return self.loader_fields if obj is not None else self.readonly_fields

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                active_ver=Subquery(
                    SurveyVersion.objects.filter(
                        survey=OuterRef("pk"), status=LifecycleStatus.ACTIVE
                    ).values("version")[:1]
                ),
                n_responses=Count("versions__responses", distinct=True),
                n_completed=Count(
                    "versions__responses",
                    filter=Q(versions__responses__status="submitted"),
                    distinct=True,
                ),
            )
        )

    @admin.display(description="Active version")
    def active(self, obj):
        return obj.active_ver or "—"

    @admin.display(description="Responses (submitted/total)")
    def responses(self, obj):
        return f"{obj.n_completed}/{obj.n_responses}"


class OptionInline(ReadOnlyMixin, admin.TabularInline):
    model = SurveyOption
    extra = 0


@admin.register(SurveyQuestion)
class QuestionAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("key", "survey_version", "section_key", "type", "order", "required")
    list_filter = ("survey_version__survey", "type")
    inlines = [OptionInline]


class AnswerInline(ReadOnlyMixin, admin.TabularInline):
    model = SurveyAnswer
    fields = ("question_key", "value", "updated_at")
    readonly_fields = fields
    extra = 0


@admin.register(SurveyResponse)
class ResponseAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("id", "survey_version", "language", "status", "started_at", "submitted_at")
    list_filter = ("survey_version__survey", "status", "language")
    readonly_fields = (
        "id",
        "survey_version",
        "language",
        "status",
        "started_at",
        "submitted_at",
        "last_question_key",
    )
    inlines = [AnswerInline]


@admin.register(SurveyContact)
class ContactAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("id", "survey_version", "language", "captured_on")
    # The address is intentionally not shown in list views.


@admin.register(SurveyConsent)
class ConsentAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("response", "consent_version", "language", "agreed_at")


class AdministrationInline(ReadOnlyMixin, admin.TabularInline):
    model = SurveyAdministration
    fields = ("due_at", "survey_version", "sent_at")
    readonly_fields = fields
    extra = 0


@admin.register(SurveyInvitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("id", "survey", "language", "active", "created_at")
    list_filter = ("survey", "active")
    inlines = [AdministrationInline]
