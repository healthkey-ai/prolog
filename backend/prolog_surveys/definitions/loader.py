"""Load definitions into the database (DEF-3, DEF-4, DEF-5, DEF-7, DEF-8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from .. import conf
from ..models import LifecycleStatus, Survey, SurveyOption, SurveyQuestion, SurveyVersion
from .normalize import checksum, normalize
from .schema import Issue, read_json, validate_schema
from .validate import has_errors, validate_semantics

DEFINITION_GLOB = "*.json"


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
def load_definition(doc: Any, *, source: str = "", activate: bool = False) -> LoadResult:
    issues = validate_definition(doc)
    if has_errors(issues):
        raise DefinitionError(issues)
    definition = normalize(doc)
    digest = checksum(definition)

    survey, _ = Survey.objects.get_or_create(
        slug=definition["slug"],
        defaults={"title": definition["title"][definition["default_language"]]},
    )
    survey.title = definition["title"][definition["default_language"]]
    survey.theme_code = definition.get("theme", "")
    survey.allow_anonymous_participation = definition["participation"]["anonymous"]
    survey.save()

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

    activated = False
    if activate and version.status != LifecycleStatus.ACTIVE:
        activate_version(version)
        activated = True
    return LoadResult(
        version=version, created=created, changed=changed, activated=activated, issues=issues
    )


@transaction.atomic
def activate_version(version: SurveyVersion) -> None:
    """Make ``version`` the single active version of its survey (DEF-4, DEF-5)."""
    if version.status == LifecycleStatus.ARCHIVED:
        raise ActivationError(
            "an archived version cannot be re-activated; load it as a new version"
        )
    pending = unreviewed_languages(version.definition)
    if pending:
        raise ActivationError(
            "cannot activate while translations are not reviewed: " + ", ".join(pending)
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
    materialize(version)


@transaction.atomic
def archive_version(version: SurveyVersion) -> None:
    version.status = LifecycleStatus.ARCHIVED
    version.archived_at = timezone.now()
    version.save(update_fields=["status", "archived_at", "updated_at"])


def materialize(version: SurveyVersion) -> None:
    """Rebuild the read-only question/option projections for a version."""
    version.questions.all().delete()
    default = version.default_language
    order = 0
    for section in version.definition["sections"]:
        for q in section["questions"]:
            question = SurveyQuestion.objects.create(
                survey_version=version,
                key=q["key"],
                section_key=section["key"],
                type=q["type"],
                order=order,
                text=q["text"][default],
                required=q.get("required", True),
            )
            order += 1
            SurveyOption.objects.bulk_create(
                [
                    SurveyOption(
                        question=question,
                        key=o["key"],
                        order=i,
                        label=o["label"][default],
                        exclusive=o.get("exclusive", False),
                        free_text=o.get("free_text", False),
                    )
                    for i, o in enumerate(q.get("options", []))
                ]
            )


def load_file(path: str | Path, *, activate: bool = False) -> LoadResult:
    path = Path(path)
    return load_definition(read_json(path), source=str(path), activate=activate)


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
