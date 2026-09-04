"""Shared helpers for definition commands."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ...definitions.schema import Issue


def report(cmd: BaseCommand, issues: list[Issue]) -> None:
    for issue in issues:
        line = str(issue)
        if issue.level == "error":
            cmd.stderr.write(cmd.style.ERROR(line))
        else:
            cmd.stdout.write(cmd.style.WARNING(line))
