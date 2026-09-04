"""JSON Schema loading and structural validation (DEF-1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .. import conf

SUPPORTED_SCHEMA_VERSIONS = (1,)
DEFINITION_SCHEMA_FILE = "survey-definition.schema.json"
THEME_SCHEMA_FILE = "theme.schema.json"


@dataclass(frozen=True, slots=True)
class Issue:
    """One validation finding. ``level`` is "error" or "warning"."""

    code: str
    path: str
    message: str
    level: str = "error"

    def __str__(self) -> str:
        return f"{self.level.upper()} {self.code} at {self.path or '$'}: {self.message}"


def _json_path(parts: list[Any]) -> str:
    out = "$"
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


@lru_cache(maxsize=4)
def _load_schema(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        schema = json.load(fh)
    Draft202012Validator.check_schema(schema)
    return schema


def definition_schema() -> dict[str, Any]:
    return _load_schema(str(conf.schema_dir() / DEFINITION_SCHEMA_FILE))


def theme_schema() -> dict[str, Any]:
    return _load_schema(str(conf.schema_dir() / THEME_SCHEMA_FILE))


def validate_against(schema: dict[str, Any], doc: Any) -> list[Issue]:
    validator = Draft202012Validator(schema)
    issues = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        issues.append(
            Issue(code="schema", path=_json_path(list(err.absolute_path)), message=err.message)
        )
    return issues


def validate_schema(doc: Any) -> list[Issue]:
    """Structural validation of a survey definition."""
    return validate_against(definition_schema(), doc)


def read_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
