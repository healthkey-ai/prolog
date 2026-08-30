"""Localise a definition for the runner (RUN-19, DEF-5)."""

from __future__ import annotations

import copy
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


def localize(definition: dict[str, Any], lang: str) -> dict[str, Any]:
    default = definition["default_language"]
    if lang not in definition["languages"]:
        lang = default

    def walk(node: Any, key: str | None = None) -> Any:
        if isinstance(node, dict):
            if key in I18N_FIELDS or key == "point_labels_item":
                return pick(node, lang, default)
            return {k: walk(v, k) for k, v in node.items()}
        if isinstance(node, list):
            if key == "point_labels":
                return [pick(p, lang, default) for p in node]
            return [walk(item, key) for item in node]
        return node

    doc = copy.deepcopy(definition)
    doc.pop("notes", None)
    doc.pop("$schema", None)
    localized = walk(doc)
    localized["language"] = lang
    return localized
