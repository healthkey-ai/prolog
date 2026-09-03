"""Django admin for the survey app.

The admin manages an instrument's **inputs** — which definition file and which
theme a survey is built from, whether they are valid, and loading them. It
deliberately does not browse the instrument's contents or its data: the
questions are the definition's, and the answers are the API's and the exports'.
Reading them here would be a second, unvalidated view of both.

Nothing a respondent's answers are interpreted against is editable here. A
version's definition, a question's text, an option's key: all of them would let
somebody produce an instrument the validator never saw.
"""

from pathlib import Path

from django.contrib import admin, messages
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from . import conf
from .definitions.loader import (
    DefinitionError,
    discover,
    load_definition,
    read_json,
    validate_definition,
)
from .definitions.validate import has_errors
from .models import (
    LifecycleStatus,
    Survey,
    SurveyAdministration,
    SurveyConsent,
    SurveyContact,
    SurveyInvitation,
    SurveyVersion,
)
from .themes import validate_theme
from .themes.registry import _theme_roots


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

    # --- verify and load ---------------------------------------------------
    # The same thing `validate_definition` and `load_definition` do from a
    # shell, for an administrator who does not have one. The validator's own
    # output is rendered rather than summarised: an administrator fixing a
    # definition needs the code, the path and the message, which is exactly
    # what the command prints.

    change_list_template = "admin/prolog_surveys/survey/change_list.html"

    def get_urls(self):
        return [
            path(
                "verify/",
                self.admin_site.admin_view(self.verify_view),
                name="prolog_surveys_survey_verify",
            ),
            *super().get_urls(),
        ]

    def _sources(self):
        """What this deployment has mounted, for the two pickers."""
        definitions = [str(p) for p in discover()]
        themes = sorted(
            str(d)
            for root in _theme_roots()
            if root.is_dir()
            for d in root.iterdir()
            if (d / "theme.json").is_file()
        )
        return definitions, themes

    def verify_view(self, request):
        definitions, themes = self._sources()
        ctx = {
            **self.admin_site.each_context(request),
            "title": "Verify and load a definition",
            "opts": self.model._meta,
            "definitions": definitions,
            "themes": themes,
            "schema_dir": str(conf.schema_dir()),
            "selected": {},
        }

        if request.method != "POST":
            return TemplateResponse(request, "admin/prolog_surveys/survey/verify.html", ctx)

        definition_path = request.POST.get("definition_path", "")
        theme_dir = request.POST.get("theme_dir", "")
        upload = request.FILES.get("definition_file")
        ctx["selected"] = {"definition_path": definition_path, "theme_dir": theme_dir}

        doc, source, read_error = None, "", ""
        if upload is not None:
            source = f"upload:{upload.name}"
            try:
                import json

                doc = json.loads(upload.read().decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                read_error = f"{upload.name} is not readable JSON: {exc}"
        elif definition_path:
            source = definition_path
            try:
                doc = read_json(Path(definition_path))
            except (OSError, ValueError) as exc:
                read_error = f"{definition_path} could not be read: {exc}"
        else:
            read_error = "Choose a mounted definition or upload one."

        if read_error:
            ctx["read_error"] = read_error
            return TemplateResponse(request, "admin/prolog_surveys/survey/verify.html", ctx)

        issues = validate_definition(doc)
        # A theme is part of what makes an instrument, so it is verified beside
        # the definition rather than in a separate trip.
        theme_issues = []
        if theme_dir:
            _, theme_issues = validate_theme(Path(theme_dir))

        blocked = has_errors(issues) or has_errors(theme_issues)
        ctx.update(
            {
                "verified": True,
                "source": source,
                "issues": issues,
                "theme_issues": theme_issues,
                "blocked": blocked,
                "slug": (doc or {}).get("slug"),
                "version": (doc or {}).get("version"),
            }
        )

        if request.POST.get("action") == "load" and not blocked:
            try:
                result = load_definition(doc, source=source)
            except DefinitionError as exc:
                ctx["load_error"] = str(exc)
                return TemplateResponse(
                    request, "admin/prolog_surveys/survey/verify.html", ctx
                )
            self.message_user(
                request,
                f"Loaded {result.version} as a draft. Activate it deliberately when it is ready.",
                messages.SUCCESS,
            )
            return redirect(reverse("admin:prolog_surveys_survey_changelist"))

        return TemplateResponse(request, "admin/prolog_surveys/survey/verify.html", ctx)


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
