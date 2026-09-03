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
from .themes import registry as theme_registry
from .themes import validate_theme
from .themes.registry import _theme_roots, discover_themes, theme_directory


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
    change_form_template = "admin/prolog_surveys/survey/change_form.html"

    def get_urls(self):
        return [
            path(
                "verify/",
                self.admin_site.admin_view(self.verify_view),
                name="prolog_surveys_survey_verify",
            ),
            *super().get_urls(),
        ]

    def _roots(self):
        """Every tree this deployment mounts, definitions and themes alike.

        Both are searched for both kinds of file: a survey's theme travels with
        the survey, so a theme under a definition root is the normal layout for
        a deployment running more than one.
        """
        return [
            Path(p) for p in (*conf.get("PROLOG_DEFINITION_DIRS"), *conf.get("PROLOG_THEME_DIRS"))
        ] + [r for r in _theme_roots()]

    def _mounted(self):
        """Each configured root, what was found under it, and whether it exists.

        Shown on the survey list because "there are no surveys" and "the
        directory this deployment points at is not there" look identical until
        somebody says which one it is.
        """
        definitions = discover()
        themes = discover_themes(self._roots())

        def under(root, paths):
            resolved = root.resolve() if root.exists() else root
            return [p for p in paths if str(p).startswith(str(resolved))]

        rows = []
        for setting, configured, found in (
            ("PROLOG_DEFINITION_DIRS", conf.get("PROLOG_DEFINITION_DIRS"), definitions),
            ("PROLOG_THEME_DIRS", conf.get("PROLOG_THEME_DIRS"), themes),
        ):
            if not configured:
                rows.append({"setting": setting, "path": "— not set —", "exists": None, "count": 0})
                continue
            for raw in configured:
                root = Path(raw)
                rows.append(
                    {
                        "setting": setting,
                        "path": str(root),
                        "exists": root.is_dir(),
                        "count": len(under(root, found)),
                    }
                )
        return rows

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(
            request, {**(extra_context or {}), "mounted": self._mounted()}
        )

    def add_view(self, request, form_url="", extra_context=None):
        """Adding a survey is loading a definition, not filling in a form.

        The fields a form would offer — slug, title, theme code — are the
        loader's, rewritten from the definition on every load, so a row typed
        here would be a survey with no version and no questions.
        """
        return redirect(reverse("admin:prolog_surveys_survey_verify"))

    def _sources(self):
        """What this deployment has mounted, for the two pickers."""
        definitions = [str(p) for p in discover()]
        themes = sorted({str(d) for d in discover_themes(self._roots())})
        return definitions, themes

    def _within_a_root(self, path: Path) -> bool:
        """Is this path inside something the deployment mounted?

        An administrator may type a path rather than pick one — a bundle can
        sit anywhere the deployment put it — and a form that reads any path on
        the filesystem is a file-disclosure hole with a staff session in front
        of it. Resolved on both sides, so `..` cannot walk out of a root.
        """
        try:
            resolved = path.resolve()
        except OSError:
            return False
        for root in self._roots():
            try:
                resolved.relative_to(root.resolve())
                return True
            except (ValueError, OSError):
                continue
        return False

    def verify_view(self, request):
        definitions, themes = self._sources()
        # Adding a version to a survey is the same act with one thing already
        # decided: which survey it belongs to. The theme comes pre-set from
        # that survey because a new version usually keeps it, and stays
        # editable because sometimes that is the point of the new version.
        slug = request.GET.get("survey") or request.POST.get("survey") or ""
        survey = Survey.objects.filter(slug=slug).first() if slug else None
        preset_theme = ""
        if survey is not None:
            theme = theme_registry.get(survey.theme_code)
            preset_theme = str(theme.directory) if theme is not None else ""

        ctx = {
            **self.admin_site.each_context(request),
            "title": (
                f"Add a version of {survey.slug}" if survey else "Verify and load a definition"
            ),
            "opts": self.model._meta,
            "definitions": definitions,
            "themes": themes,
            "schema_dir": str(conf.schema_dir()),
            "for_survey": survey,
            "selected": {"theme_dir": preset_theme} if survey else {},
        }

        if request.method != "POST":
            return TemplateResponse(request, "admin/prolog_surveys/survey/verify.html", ctx)

        definition_path = request.POST.get("definition_path", "")
        theme_dir = request.POST.get("theme_dir", "")
        upload = request.FILES.get("definition_file")
        ctx["selected"] = {"definition_path": definition_path, "theme_dir": theme_dir}

        doc, source, read_error = None, "", ""
        for field, value in (("definition", definition_path), ("theme", theme_dir)):
            if value and not self._within_a_root(Path(value)):
                ctx["read_error"] = (
                    f"The {field} path is outside every directory this deployment mounts. "
                    "Add it to PROLOG_DEFINITION_DIRS or PROLOG_THEME_DIRS, or upload the file."
                )
                return TemplateResponse(request, "admin/prolog_surveys/survey/verify.html", ctx)

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
            # Either the folder or its theme.json: an administrator points at
            # whichever they have in front of them.
            _, theme_issues = validate_theme(theme_directory(Path(theme_dir)))

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

        # A definition names its own survey. Adding a version to one survey
        # from a definition slugged for another would quietly create a second
        # survey, which is not what the button said.
        if survey is not None and (doc or {}).get("slug") != survey.slug:
            ctx["blocked"] = True
            ctx["slug_mismatch"] = (doc or {}).get("slug") or "—"
            return TemplateResponse(request, "admin/prolog_surveys/survey/verify.html", ctx)

        if request.POST.get("action") == "load" and not blocked:
            try:
                result = load_definition(doc, source=source)
            except DefinitionError as exc:
                ctx["load_error"] = str(exc)
                return TemplateResponse(request, "admin/prolog_surveys/survey/verify.html", ctx)
            # Say which of the three things happened. "Loaded" over a version
            # that already existed unchanged reads as success and leaves an
            # administrator wondering why nothing moved.
            if result.created:
                note, level = (
                    f"Created {result.version} as a draft. "
                    "Activate it deliberately when it is ready.",
                    messages.SUCCESS,
                )
            elif result.changed:
                note, level = (
                    f"Updated the existing draft {result.version} from this definition.",
                    messages.SUCCESS,
                )
            else:
                note, level = (
                    f"{result.version} already exists with this exact content. "
                    "Nothing was written. To change a published version, bump the "
                    "version in the definition — a response records which version "
                    "it answered.",
                    messages.WARNING,
                )
            self.message_user(request, note, level)
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
