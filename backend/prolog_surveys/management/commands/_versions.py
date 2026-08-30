import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO

from django.core.management.base import CommandError

from ...models import Survey, SurveyVersion


def resolve_version(slug: str, version: str | None) -> SurveyVersion:
    try:
        survey = Survey.objects.get(slug=slug)
    except Survey.DoesNotExist as exc:
        raise CommandError(f"unknown survey '{slug}'") from exc
    if version:
        try:
            return survey.versions.get(version=version)
        except SurveyVersion.DoesNotExist as exc:
            raise CommandError(f"unknown version '{version}' of '{slug}'") from exc
    active = survey.active_version
    if active is None:
        raise CommandError(f"'{slug}' has no active version; pass --survey-version")
    return active


def add_version_arguments(parser) -> None:
    parser.add_argument("slug")
    parser.add_argument("--survey-version", default=None, help="Defaults to the active version")
    parser.add_argument("--out", default="-", help="File path or - for stdout")


@contextmanager
def csv_output(path: str) -> Iterator[IO[str]]:
    """``--out``: stdout for ``-``, else a UTF-8 file opened for csv writing."""
    if path == "-":
        yield sys.stdout
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        yield fh
