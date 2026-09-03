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

import json
from pathlib import Path
from types import SimpleNamespace

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.http import urlencode

from . import conf
from .definitions.loader import (
    DefinitionError,
    ResponsesExist,
    discover,
    load_definition,
    matches_source,
    publish_version,
    read_json,
    validate_definition,
)
from .definitions.validate import has_errors
from .models import (
    LifecycleStatus,
    ResponseStatus,
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

# A browser does not send an uploaded file twice, so a definition verified from
# an upload has to be held somewhere for the press that loads it. The session:
# it is per-administrator, it survives the redirect every other outcome takes,
# and it is not shared between workers the way a local-memory cache is.
UPLOAD_STASH = "prolog_surveys.verified_upload"
UPLOAD_STASH_LIMIT = 512 * 1024


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class VersionInline(ReadOnlyMixin, admin.TabularInline):
    """The survey's versions, listed and nothing more.

    ReadOnlyMixin is what removes Django's own "Add another Survey version"
    row. That link offered a blank version to type by hand: a row with no
    definition, no questions and nothing validated — the second, unvalidated
    engine this admin exists to avoid. A version comes from a definition, and
    the link that adds one is in the page's object tools.
    """

    model = SurveyVersion
    fields = ("version", "status", "schema_version", "activated_at", "content", "source")
    readonly_fields = fields

    @admin.display(description="Content")
    def content(self, obj):
        """Whether this version's wording can still change, and how to end that.

        Activation is a separate column because it answers a separate
        question: which version respondents are being given, not whether what
        it says is final.
        """
        if obj.pk is None:  # pragma: no cover - Django renders no empty row
            return "—"
        if obj.is_published:
            return f"Published {obj.published_at:%Y-%m-%d %H:%M} — frozen"
        if obj.status == LifecycleStatus.ARCHIVED:
            return "Archived — frozen"
        # Re-load reads the file this version came from again; publish ends
        # both. The pair is the whole loop of getting an instrument right, so
        # they sit together on the row rather than in two different places.
        query = urlencode({"survey": obj.survey.slug, "version": obj.version})
        return format_html(
            '<a class="button" href="{}?{}">Re-load…</a> <a class="button" href="{}">Publish…</a>',
            reverse("admin:prolog_surveys_survey_verify"),
            query,
            reverse("admin:prolog_surveys_surveyversion_publish", args=[obj.pk]),
        )

    extra = 0
    max_num = 0
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
            path(
                "publish/<int:version_id>/",
                self.admin_site.admin_view(self.publish_view),
                name="prolog_surveys_surveyversion_publish",
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

    def _verify_into(self, ctx, doc, source, theme_dir) -> bool:
        """Validate a definition (and its theme) into the page's context.

        The same work whether an administrator asked for it or arrived from a
        version's Re-load link with the file it came from already chosen.
        """
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
        return blocked

    def _discardable(self, doc):
        """The responses a load of ``doc`` would have to delete, if any.

        Recomputed for the page rather than remembered from the request that
        found out, so the answer survives a redirect — and a Back button, which
        must never mean "submit that again".
        """
        version = SurveyVersion.objects.filter(
            survey__slug=doc.get("slug"), version=doc.get("version")
        ).first()
        if version is None or not version.is_mutable:
            return None
        if matches_source(version, doc):
            return None  # the same document: a load would write nothing
        total = version.responses.count()
        if not total:
            return None
        return SimpleNamespace(
            version=version,
            total=total,
            submitted=version.responses.filter(status=ResponseStatus.SUBMITTED).count(),
        )

    def _hold_upload(self, request, name: str, doc) -> bool:
        """Keep a verified upload for the next press, if it is small enough."""
        if len(json.dumps(doc)) > UPLOAD_STASH_LIMIT:
            return False
        request.session[UPLOAD_STASH] = {"name": name, "doc": doc}
        return True

    def _held_upload(self, request, *, release=False):
        """The upload being worked on, as ``(doc, source)`` or ``(None, "")``."""
        held = (
            request.session.pop(UPLOAD_STASH, None)
            if release
            else request.session.get(UPLOAD_STASH)
        )
        if not held:
            return None, ""
        return held["doc"], f"upload:{held['name']}"

    def _form_url(self, **params) -> str:
        query = urlencode({k: v for k, v in params.items() if v})
        url = reverse("admin:prolog_surveys_survey_verify")
        return f"{url}?{query}" if query else url

    def _may_write(self, request, doc=None) -> bool:
        """May this user load *this* document?

        ``admin_view`` asks only for a staff session, which is not a permission
        to write: loading replaces what an instrument says and can discard the
        responses given against it. Creating a survey is an add and re-loading
        one is a change, so the document decides which of the two is required.
        """
        slug = (doc or {}).get("slug")
        if slug and Survey.objects.filter(slug=slug).exists():
            return self.has_change_permission(request)
        return self.has_add_permission(request)

    def verify_view(self, request):
        """Verify a definition, and load it.

        Everything that goes wrong is said in one place — a refusal, an
        unreadable file, a path outside the mounted roots, a version that is
        already there — and the page it is said on is always reached by a GET.
        A POST decides and then redirects, so Back is a page and not a
        resubmission, and reloading the browser repeats nothing.
        """
        # Reading a mounted definition is admin content, and loading one is a
        # write; neither is implied by a staff session alone. Add is here
        # because creating a survey is what add permission is for, and Django
        # does not read it as implying view (has_view_permission covers change).
        if not (self.has_view_permission(request) or self.has_add_permission(request)):
            raise PermissionDenied
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

        # Re-loading is this same act with one more thing already decided:
        # which version is being replaced, and therefore which file to read
        # again. Only a source this deployment still mounts is offered — a
        # version loaded from an upload, or from a directory since unmounted,
        # falls back to the pickers.
        label = request.GET.get("version") or request.POST.get("version") or ""
        reload_of = survey.versions.filter(version=label).first() if survey and label else None

        chosen = request.GET.get("definition_path") or ""
        if chosen not in definitions:
            # Only a file this deployment mounts can be chosen by a link; a
            # query parameter must not become a way to read anything else.
            chosen = ""
        if not chosen and reload_of is not None and reload_of.source in definitions:
            chosen = reload_of.source
        chosen_theme = request.GET.get("theme_dir") or ""
        if chosen_theme and not self._within_a_root(Path(chosen_theme)):
            chosen_theme = ""

        selected = {"theme_dir": chosen_theme or preset_theme}
        if chosen:
            selected["definition_path"] = chosen

        if reload_of is not None:
            title = f"Re-load {reload_of.survey.slug} {reload_of.version}"
        elif survey is not None:
            title = f"Add a version of {survey.slug}"
        else:
            title = "Verify and load a definition"

        ctx = {
            **self.admin_site.each_context(request),
            "title": title,
            "opts": self.model._meta,
            "definitions": definitions,
            "themes": themes,
            "schema_dir": str(conf.schema_dir()),
            "for_survey": survey,
            "reload_of": reload_of,
            "selected": selected,
        }

        def page():
            return TemplateResponse(request, "admin/prolog_surveys/survey/verify.html", ctx)

        def say(level, text):
            # Django's own message list, which the admin already renders above
            # the content: one slot, one style, whether the outcome is reached
            # on this page or after a redirect. A second list of our own looked
            # different and stacked underneath the first.
            self.message_user(request, text, level)

        if request.method != "POST":
            # A POST has already said what happened; repeating the verdict here
            # would print it twice.
            quiet = request.GET.get("said") == "1"
            path = selected.get("definition_path")
            doc, source = None, ""
            if request.GET.get("uploaded") == "1":
                doc, source = self._held_upload(request)
                if doc is None:
                    say(
                        messages.WARNING,
                        "That upload is no longer held — choose the file again.",
                    )
                    return page()
                ctx["uploaded"] = source.removeprefix("upload:")
            elif path:
                source = path
                try:
                    doc = read_json(Path(path))
                except (OSError, ValueError) as exc:
                    say(messages.ERROR, f"{path} could not be read: {exc}")
                    return page()
            if doc is not None:
                blocked = self._verify_into(ctx, doc, source, selected["theme_dir"])
                ctx["discardable"] = None if blocked else self._discardable(doc)
                if quiet:
                    return page()
                if blocked:
                    say(messages.ERROR, "This definition has errors. Nothing was written.")
                elif reload_of is not None and doc.get("version") != reload_of.version:
                    say(
                        messages.WARNING,
                        f"That file is version {doc.get('version')}, not {reload_of.version}. "
                        f"Loading it adds a version rather than replacing {reload_of.version}.",
                    )
            return page()

        definition_path = request.POST.get("definition_path", "")
        theme_dir = request.POST.get("theme_dir", "")
        upload = request.FILES.get("definition_file")
        ctx["selected"] = {"definition_path": definition_path, "theme_dir": theme_dir}

        def bounce(level, text, *, uploaded=""):
            """Say it, then land the administrator on a GET of this form.

            Every outcome goes through here, so no page an administrator can
            press Back to was produced by a POST.
            """
            say(level, text)
            return redirect(
                self._form_url(
                    survey=slug,
                    version=label,
                    definition_path="" if uploaded else definition_path,
                    theme_dir=theme_dir,
                    uploaded=uploaded,
                    said="1",
                )
            )

        for field, value in (("definition", definition_path), ("theme", theme_dir)):
            if value and not self._within_a_root(Path(value)):
                # The path is the problem, so the form comes back without it —
                # by a redirect, like every other outcome, so Back is a page.
                say(
                    messages.ERROR,
                    f"The {field} path is outside every directory this deployment mounts. "
                    "Add it to PROLOG_DEFINITION_DIRS or PROLOG_THEME_DIRS, or upload the file.",
                )
                return redirect(self._form_url(survey=slug, version=label, said="1"))

        # A fresh file wins; then a mounted one; then the upload verified on
        # the press before this one, which the browser did not send again.
        doc, source, held = None, "", False
        if upload is not None:
            source = f"upload:{upload.name}"
            try:
                doc = json.loads(upload.read().decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                request.session.pop(UPLOAD_STASH, None)
                return bounce(messages.ERROR, f"{upload.name} is not readable JSON: {exc}")
        elif definition_path:
            source = definition_path
            try:
                doc = read_json(Path(definition_path))
            except (OSError, ValueError) as exc:
                return bounce(messages.ERROR, f"{definition_path} could not be read: {exc}")
        elif request.POST.get("uploaded") == "1":
            doc, source = self._held_upload(request)
            held = doc is not None
            if doc is None:
                return bounce(
                    messages.ERROR,
                    "That upload is no longer held. Choose the file again — a browser "
                    "does not send it twice.",
                )
        else:
            return bounce(messages.ERROR, "Choose a mounted definition or upload one.")

        uploaded_name = ""
        if upload is not None:
            uploaded_name = upload.name if self._hold_upload(request, upload.name, doc) else ""
        elif held:
            uploaded_name = source.removeprefix("upload:")
        if upload is not None and not uploaded_name:
            say(
                messages.WARNING,
                f"{upload.name} is too large to hold between presses, so Verify cannot be "
                "followed by Load. Press Load as draft with the file chosen: it verifies "
                "first and writes nothing if there are errors.",
            )
        ctx["uploaded"] = uploaded_name

        blocked = self._verify_into(ctx, doc, source, theme_dir)
        if blocked:
            return bounce(
                messages.ERROR,
                "Refused: this definition has errors. Nothing was written.",
                uploaded="1" if uploaded_name else "",
            )

        # A definition names its own survey. Adding a version to one survey
        # from a definition slugged for another would quietly create a second
        # survey, which is not what the button said.
        if survey is not None and doc.get("slug") != survey.slug:
            ctx["blocked"] = True
            return bounce(
                messages.ERROR,
                f"That definition is for '{doc.get('slug') or '—'}', not '{survey.slug}'. "
                "Loading it here would create a second survey; use Add survey for that.",
                uploaded="1" if uploaded_name else "",
            )

        action = request.POST.get("action")
        if action in ("load", "load_discarding") and not self._may_write(request, doc):
            return bounce(
                messages.ERROR,
                "You do not have permission to load definitions for this survey. "
                "Nothing was written.",
                uploaded="1" if uploaded_name else "",
            )
        if action not in ("load", "load_discarding"):
            return redirect(
                self._form_url(
                    survey=slug,
                    version=label,
                    definition_path="" if uploaded_name else definition_path,
                    theme_dir=theme_dir,
                    uploaded="1" if uploaded_name else "",
                )
            )

        try:
            result = load_definition(
                doc, source=source, discard_responses=action == "load_discarding"
            )
        except ResponsesExist as exc:
            # Not a refusal: the version is unpublished, so those responses are
            # the test data from trying the instrument out. Only the person
            # loading knows that, so the page asks rather than deciding.
            ctx["discardable"] = exc
            return bounce(
                messages.WARNING,
                f"There are {exc.total} response(s) against {exc.version}, "
                f"{exc.submitted} of them submitted. It is not published, so they are "
                "test data — press \u201cDiscard responses and load\u201d to replace the "
                "definition and delete them, or bump the version in the file to keep them.",
                uploaded="1" if uploaded_name else "",
            )
        except DefinitionError as exc:
            ctx["blocked"] = True
            return bounce(messages.ERROR, str(exc), uploaded="1" if uploaded_name else "")

        if not result.created and not result.changed:
            # Not an error and not a success: nothing happened, and saying
            # "loaded" would leave an administrator wondering why nothing moved.
            # Which advice follows depends on why — telling somebody re-loading
            # an unpublished version to bump it sends them to fix a rule they
            # have not hit.
            return bounce(
                messages.WARNING,
                f"Nothing to load: the file is identical to {result.version} as it "
                + (
                    "already stands. It is published, so a change to it is a new version — "
                    "bump the version in the file."
                    if result.version.is_published
                    else "already stands, so nothing was written. Edit the file and re-load, "
                    "or bump the version in it to add a second version."
                ),
                uploaded="1" if uploaded_name else "",
            )

        note = (
            f"Created {result.version} as a draft. Activate it deliberately when it is ready."
            if result.created
            else f"Re-loaded {result.version} from this definition. Publish it when the "
            "wording is settled; until then it can be re-loaded again."
        )
        request.session.pop(UPLOAD_STASH, None)
        self.message_user(request, note, messages.SUCCESS)
        # Only a load that wrote something navigates, and it lands on what it
        # wrote rather than on a list of everything.
        return redirect(
            reverse("admin:prolog_surveys_survey_change", args=[result.version.survey_id])
        )

    def publish_view(self, request, version_id):
        """Freeze a version's content, deliberately and on the record.

        A GET says what publishing costs — it cannot be undone, and the
        responses stop being test data — because the only way back from a
        mistake here is a new version.
        """
        version = get_object_or_404(SurveyVersion.objects.select_related("survey"), pk=version_id)
        if not self.has_change_permission(request, version.survey):
            raise PermissionDenied
        back = redirect(reverse("admin:prolog_surveys_survey_change", args=[version.survey_id]))

        if version.is_published:
            self.message_user(
                request,
                f"{version} was already published on {version.published_at:%Y-%m-%d %H:%M}.",
                messages.WARNING,
            )
            return back
        if version.status == LifecycleStatus.ARCHIVED:
            self.message_user(
                request,
                f"{version} is archived: its content is frozen already, and publishing it "
                "now would say it was current when it is not.",
                messages.WARNING,
            )
            return back

        total = version.responses.count()
        if request.method != "POST":
            return TemplateResponse(
                request,
                "admin/prolog_surveys/survey/publish.html",
                {
                    **self.admin_site.each_context(request),
                    "title": f"Publish {version}",
                    "opts": self.model._meta,
                    "version": version,
                    "responses": total,
                    "submitted": version.responses.filter(status=ResponseStatus.SUBMITTED).count(),
                },
            )

        publish_version(version)
        self.message_user(
            request,
            f"Published {version}. Its content is frozen"
            + (
                f", and its {total} response(s) are answers now, not test data."
                if total
                else "; a change from here is a new version."
            ),
            messages.SUCCESS,
        )
        return back


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
