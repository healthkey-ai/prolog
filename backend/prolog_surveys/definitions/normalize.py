"""Normalisation of a validated definition (DEF-8).

Fills schema defaults so the runner and engine never need to reason about
absent keys, and produces a deterministic serialisation for checksums.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

PRESENTATION_DEFAULTS = {
    "mode": "question",
    "overview": True,
    "section_interstitials": True,
    "skip_policy": "soft",
    "progress": "bar",
}
PARTICIPATION_DEFAULTS = {"anonymous": False, "resume": "account"}


def normalize(definition: dict[str, Any]) -> dict[str, Any]:
    doc = copy.deepcopy(definition)
    doc.pop("$schema", None)
    doc.setdefault("schema_version", 1)
    doc.setdefault("translation_status", {})

    participation = {**PARTICIPATION_DEFAULTS, **doc.get("participation", {})}
    if participation["anonymous"] and "resume" not in doc.get("participation", {}):
        participation["resume"] = "browser_token"
    doc["participation"] = participation
    doc["presentation"] = {**PRESENTATION_DEFAULTS, **doc.get("presentation", {})}
    if "consent" in doc:
        doc["consent"].setdefault("required", True)

    for section in doc["sections"]:
        section.setdefault("visible_if", [])
        for q in section["questions"]:
            q.setdefault("required", q["type"] != "info")
            q.setdefault("visible_if", [])
            q.setdefault("config", {})
            q.setdefault("options", [])
            for o in q["options"]:
                o.setdefault("exclusive", False)
                o.setdefault("free_text", False)
            if q["type"] == "text" and "multiline" not in q["config"]:
                q["config"]["multiline"] = q["config"].get("max_length", 0) > 200
            if q["type"] == "multi":
                q["config"].setdefault("min_selections", 1)
    return doc


def canonical_json(doc: dict[str, Any]) -> str:
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def checksum(doc: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(doc).encode("utf-8")).hexdigest()


def source_checksum(definition: dict[str, Any]) -> str:
    """Digest of the authored document (``$schema`` aside), independent of the
    defaults ``normalize`` fills in: the loader's identity for "unchanged"."""
    return checksum({k: v for k, v in definition.items() if k != "$schema"})
