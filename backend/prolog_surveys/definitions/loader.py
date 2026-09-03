"""Load definitions into the database (DEF-3, DEF-4, DEF-5, DEF-7, DEF-8)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from .. import conf
from ..engine.visibility import iter_questions
from ..models import LifecycleStatus, Survey, SurveyOption, SurveyQuestion, SurveyVersion
from .normalize import checksum, normalize, source_checksum
from .schema import Issue, read_json, validate_schema
from .validate import has_errors, validate_semantics

DEFINITION_GLOB = "*.json"
log = logging.getLogger(__name__)


class DefinitionError(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("; ".join(str(i) for i in issues if i.level == "error"))


class ActivationError(Exception):
    pass


@dataclass
class LoadResult:
    version: SurveyVersion
    created: bool
    changed: bool
    activated: bool
    issues: list[Issue] = field(default_factory=list)

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]


def validate_definition(doc: Any, *, profile: str | None = None) -> list[Issue]:
    """Structural then semantic validation; semantic rules run only if structure is sound."""
    issues = validate_schema(doc)
    if has_errors(issues):
        return issues
    return issues + validate_semantics(doc, profile=profile or conf.profile())


def unreviewed_languages(definition: dict[str, Any]) -> list[str]:
    default = definition["default_language"]
    status = definition.get("translation_status", {})
    return [
        lang
        for lang in definition["languages"]
        if lang != default and status.get(lang) != "reviewed"
    ]


@transaction.atomic
def load_definition(
    doc: Any, *, source: str = "", activate: bool = False, allow_unreviewed: bool = False
) -> LoadResult:
    issues = validate_definition(doc)
    if has_errors(issues):
        raise DefinitionError(issues)
    definition = normalize(doc)
    # The checksum identifies the *source* document: the normalised form is
    # derived from it, and a new normaliser default must not make an unchanged
    # file look edited (and refuse to re-load its active version).
    digest = source_checksum(doc)

    survey, _ = Survey.objects.get_or_create(
        slug=definition["slug"],
        defaults={"title": definition["title"][definition["default_language"]]},
    )

    version, created = SurveyVersion.objects.select_for_update().get_or_create(
        survey=survey,
        version=definition["version"],
        defaults={
            "definition": definition,
            "checksum": digest,
            "schema_version": definition["schema_version"],
            "source": source,
        },
    )
    changed = created
    if not created and version.checksum != digest and version.checksum == checksum(definition):
        # Row written while the checksum still covered the normalised document:
        # the same source, so migrate the digest rather than report an edit.
        version.checksum = digest
        version.save(update_fields=["checksum", "updated_at"])
    if not created and version.checksum != digest:
        if not version.is_mutable:
            raise DefinitionError(
                [
                    Issue(
                        "immutable",
                        "$.version",
                        f"version {version.version} is {version.status}; bump the version to change it",
                    )
                ]
            )
        version.definition = definition
        version.checksum = digest
        version.schema_version = definition["schema_version"]
        version.source = source
        version.save()
        changed = True
    elif not created and version.definition != definition:
        # Same source, newer normaliser: refresh the derived document so the
        # engine never reads a stored version missing a default it now relies on.
        version.definition = definition
        version.schema_version = definition["schema_version"]
        version.save(update_fields=["definition", "schema_version", "updated_at"])

    activated = False
    if activate and version.status != LifecycleStatus.ACTIVE:
        activate_version(version, allow_unreviewed=allow_unreviewed)
        activated = True
    elif version.status == LifecycleStatus.ACTIVE or survey.active_version is None:
        # Survey-level fields mirror the active version; a draft may only seed
        # them while nothing is live (it must not retarget a running survey).
        _sync_survey(version)
    return LoadResult(
        version=version, created=created, changed=changed, activated=activated, issues=issues
    )


@transaction.atomic
def activate_version(version: SurveyVersion, *, allow_unreviewed: bool = False) -> None:
    """Make ``version`` the single active version of its survey (DEF-4, DEF-5).

    Two different things get a version past the translation gate, and they mean
    different things:

    * ``allow_unreviewed`` — "I am previewing this." A CLI flag, for local and
      staging review of machine-translated content. It logs loudly and must
      never be used for a launch: the respondent is shown nothing.
    * ``PROLOG_MACHINE_LANGUAGES`` — "respondents will read a machine
      translation of this language, and that is intended." A deployment
      setting, empty by default, and the runner *discloses* the machine origin
      to anyone reading one of those languages.

    For a short, plain-language instrument a machine translation is usually
    better for the respondent than no translation at all — as long as they are
    told which they are reading.
    """
    # Serialise activations of one survey: two concurrent ones would both read
    # the same current version and race the one-active-version constraint.
    Survey.objects.select_for_update().get(pk=version.survey_id)
    version.refresh_from_db(fields=["status"])
    if version.status == LifecycleStatus.ARCHIVED:
        raise ActivationError(
            "an archived version cannot be re-activated; load it as a new version"
        )
    pending = unreviewed_languages(version.definition)
    accepted = conf.machine_languages()
    blocking = [lang for lang in pending if lang not in accepted]
    if blocking and not allow_unreviewed:
        raise ActivationError(
            "cannot activate while translations are not reviewed: "
            + ", ".join(blocking)
            + ". Get them reviewed, or name them in PROLOG_MACHINE_LANGUAGES to offer "
            "them as machine translations — which the runner discloses to respondents."
        )
    if blocking:
        log.warning(
            "activating %s with UNREVIEWED translations (%s) — review use only, not for launch",
            version,
            ", ".join(blocking),
        )
    if disclosed := [lang for lang in pending if lang in accepted]:
        log.info(
            "activating %s offering %s as machine translations; respondents are told so",
            version,
            ", ".join(disclosed),
        )
    now = timezone.now()
    for current in version.survey.versions.filter(status=LifecycleStatus.ACTIVE).exclude(
        pk=version.pk
    ):
        current.status = LifecycleStatus.ARCHIVED
        current.archived_at = now
        current.save(update_fields=["status", "archived_at", "updated_at"])
    version.status = LifecycleStatus.ACTIVE
    version.published_at = now
    version.save(update_fields=["status", "published_at", "updated_at"])
    _sync_survey(version)
    materialize(version)


def _sync_survey(version: SurveyVersion) -> None:
    """Survey-level fields mirror the active version only; a draft must not
    retarget the live survey's title, theme or participation mode."""
    definition = version.definition
    survey = version.survey
    survey.title = definition["title"][definition["default_language"]]
    survey.theme_code = definition.get("theme", "")
    survey.allow_anonymous_participation = definition["participation"]["anonymous"]
    survey.save(
        update_fields=["title", "theme_code", "allow_anonymous_participation", "updated_at"]
    )


@transaction.atomic
def archive_version(version: SurveyVersion) -> None:
    version.status = LifecycleStatus.ARCHIVED
    version.archived_at = timezone.now()
    version.save(update_fields=["status", "archived_at", "updated_at"])


def materialize(version: SurveyVersion) -> None:
    """Rebuild the read-only question/option projections for a version."""
    version.questions.all().delete()
    default = version.default_language
    questions = [
        SurveyQuestion(
            survey_version=version,
            key=q["key"],
            section_key=section["key"],
            type=q["type"],
            order=order,
            text=q["text"][default],
            required=q.get("required", True),
        )
        for order, (_, section, q) in enumerate(iter_questions(version.definition))
    ]
    # PostgreSQL returns the new pks (DEP-6: no other backend), so one insert
    # per table instead of one per question.
    SurveyQuestion.objects.bulk_create(questions)
    by_key = {q.key: q for q in questions}
    SurveyOption.objects.bulk_create(
        [
            SurveyOption(
                question=by_key[q["key"]],
                key=o["key"],
                order=i,
                label=o["label"][default],
                exclusive=o.get("exclusive", False),
                free_text=o.get("free_text", False),
            )
            for _, _, q in iter_questions(version.definition)
            for i, o in enumerate(q.get("options", []))
        ]
    )


def load_file(
    path: str | Path, *, activate: bool = False, allow_unreviewed: bool = False
) -> LoadResult:
    path = Path(path)
    return load_definition(
        read_json(path), source=str(path), activate=activate, allow_unreviewed=allow_unreviewed
    )


def discover(paths: list[str | Path] | None = None) -> list[Path]:
    """Definition files in the given paths (files or directories) or PROLOG_DEFINITION_DIRS."""
    roots = [Path(p) for p in (paths or conf.get("PROLOG_DEFINITION_DIRS"))]
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(sorted(root.glob(DEFINITION_GLOB)))
        elif root.is_file():
            files.append(root)
    return files
