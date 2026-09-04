"""Localise a definition for the runner (RUN-19, DEF-5)."""

from __future__ import annotations

from typing import Any

I18N_FIELDS = {
    "title",
    "intro",
    "completion",
    "text",
    "help",
    "label",
    "description",
    "min_label",
    "max_label",
}


def pick(obj: dict[str, str], lang: str, default: str) -> str:
    return obj.get(lang) or obj.get(default) or next(iter(obj.values()), "")


def resolve_language(definition: dict[str, Any], lang: str | None) -> str:
    """``lang`` when the definition offers it, else the default language."""
    default = definition["default_language"]
    return lang if lang and lang in definition["languages"] else default


def localize(definition: dict[str, Any], lang: str) -> dict[str, Any]:
    default = definition["default_language"]
    lang = resolve_language(definition, lang)

    def walk(node: Any, key: str | None = None) -> Any:
        if isinstance(node, dict):
            if key in I18N_FIELDS:
                return pick(node, lang, default)
            return {k: walk(v, k) for k, v in node.items()}
        if isinstance(node, list):
            if key == "point_labels":
                return [pick(p, lang, default) for p in node]
            return [walk(item, key) for item in node]
        return node

    # walk() rebuilds every container, so the source definition is never mutated.
    localized = walk({k: v for k, v in definition.items() if k not in ("notes", "$schema")})
    localized["language"] = lang
    return localized
