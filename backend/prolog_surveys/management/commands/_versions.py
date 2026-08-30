from django.core.management.base import CommandError

from ...models import LifecycleStatus, Survey, SurveyVersion


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
    active = survey.versions.filter(status=LifecycleStatus.ACTIVE).first()
    if active is None:
        raise CommandError(f"'{slug}' has no active version; pass --version")
    return active
