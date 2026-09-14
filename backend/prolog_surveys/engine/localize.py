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
    "not_applicable",
}


def pick(obj: dict[str, str], lang: str, default: str) -> str:
    return obj.get(lang) or obj.get(default) or next(iter(obj.values()), "")


def resolve_language(definition: dict[str, Any], lang: str | None) -> str:
    """The offered language ``lang`` names, else the default language.

    A browser says ``es-ES`` or ``pt-BR``; a survey offers ``es`` and ``pt``.
    The region is not a different language for the purpose of choosing which
    text to show, so a tag resolves by its base when the exact tag is not
    offered. (An offered regional tag still matches exactly first.)
    """
    default = definition["default_language"]
    if not lang:
        return default
    offered = definition["languages"]
    if lang in offered:
        return lang
    base = lang.lower().split("-")[0]
    return base if base in offered else default


def language_from_accept_header(definition: dict[str, Any], header: str | None) -> str | None:
    """The first language in an ``Accept-Language`` header the survey offers, or None.

    Browsers send this on every request, most preferred first, and it is the
    only thing a fresh visitor has said about the language they read. Nothing
    here falls back: a header naming only languages the survey does not offer
    resolves to None, and the caller decides what that means.
    """
    if not header:
        return None
    offered = definition["languages"]
    for tag in _accept_language_tags(header):
        if tag in offered:
            return tag
        base = tag.split("-")[0]
        if base in offered:
            return base
    return None


def _accept_language_tags(header: str) -> list[str]:
    """Tags from an ``Accept-Language`` header, most preferred first.

    Kept free of Django (this is engine code): the grammar is
    ``tag[;q=weight], ...``, weights default to 1, order breaks ties. A
    malformed weight counts as 0 rather than failing the request.
    """
    weighted: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        tag = tag.strip().lower()
        if not tag or tag == "*":
            continue
        weight = 1.0
        params = params.strip()
        if params.startswith("q="):
            try:
                weight = float(params[2:])
            except ValueError:
                weight = 0.0
        if weight > 0:
            weighted.append((-weight, index, tag))
    return [tag for _, _, tag in sorted(weighted)]


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
