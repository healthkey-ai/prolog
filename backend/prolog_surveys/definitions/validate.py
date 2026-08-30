"""Semantic validation of a survey definition (DEF-6, DEF-10).

Runs after structural validation. Every rule produces an ``Issue`` with a
JSON path; errors block loading, warnings are reported only.

The central rule is the DAG rule (DEF-10): questions are nodes, every
``visible_if`` condition and ``rows_from`` reference is an edge, and an edge
may only point to a question that appears *earlier* in presentation order.
Because all edges point backward the graph is acyclic by construction and
presentation order is the topological order the engine evaluates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schema import SUPPORTED_SCHEMA_VERSIONS, Issue

OPTION_TYPES = {"single", "dropdown", "multi", "ranking"}
SINGLE_VALUED = {"single", "dropdown", "scale"}
MULTI_VALUED = {"multi", "ranking"}
ANSWERABLE = {
    "single",
    "dropdown",
    "multi",
    "scale",
    "ranking",
    "matrix",
    "text",
    "number",
    "date",
    "email",
}

CONFIG_BY_TYPE: dict[str, set[str]] = {
    "info": set(),
    "single": set(),
    "dropdown": {"options_source"},
    "multi": {"max_selections", "min_selections"},
    "scale": {"scale"},
    "ranking": {"optional_items"},
    "matrix": {"scale", "rows_from", "rows"},
    "text": {"max_length", "multiline"},
    "number": {"min_value", "max_value", "integer"},
    "date": {"min_date", "max_date"},
    "email": {"store_separately", "link_identity"},
}


@dataclass
class QuestionInfo:
    key: str
    index: int
    section_index: int
    section_key: str
    type: str
    question: dict[str, Any]
    path: str
    option_keys: list[str] = field(default_factory=list)


@dataclass
class Graph:
    """Dependency graph of a definition; ``edges[k]`` = keys ``k`` depends on."""

    order: list[str]
    index: dict[str, int]
    edges: dict[str, set[str]]
    dependents: dict[str, set[str]]


def build_graph(definition: dict[str, Any]) -> Graph:
    order: list[str] = []
    edges: dict[str, set[str]] = {}
    for section in definition["sections"]:
        for q in section["questions"]:
            order.append(q["key"])
            deps = {c["question"] for c in q.get("visible_if", [])}
            deps |= {c["question"] for c in section.get("visible_if", [])}
            rows_from = (q.get("config") or {}).get("rows_from")
            if rows_from:
                deps.add(rows_from)
            edges[q["key"]] = deps
    index = {k: i for i, k in enumerate(order)}
    dependents: dict[str, set[str]] = {k: set() for k in order}
    for k, deps in edges.items():
        for d in deps:
            if d in dependents:
                dependents[d].add(k)
    return Graph(order=order, index=index, edges=edges, dependents=dependents)


def _walk_i18n(definition: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Every i18n object in the definition with its path."""
    found: list[tuple[str, dict[str, Any]]] = []

    def add(path: str, value: Any) -> None:
        if isinstance(value, dict):
            found.append((path, value))

    for key in ("title", "intro", "completion"):
        add(f"$.{key}", definition.get(key))
    if consent := definition.get("consent"):
        add("$.consent.text", consent.get("text"))
    for si, section in enumerate(definition["sections"]):
        sp = f"$.sections[{si}]"
        add(f"{sp}.title", section.get("title"))
        add(f"{sp}.description", section.get("description"))
        for qi, q in enumerate(section["questions"]):
            qp = f"{sp}.questions[{qi}]"
            add(f"{qp}.text", q.get("text"))
            add(f"{qp}.help", q.get("help"))
            for oi, o in enumerate(q.get("options", [])):
                add(f"{qp}.options[{oi}].label", o.get("label"))
            cfg = q.get("config") or {}
            if scale := cfg.get("scale"):
                add(f"{qp}.config.scale.min_label", scale.get("min_label"))
                add(f"{qp}.config.scale.max_label", scale.get("max_label"))
                for pi, p in enumerate(scale.get("point_labels", [])):
                    add(f"{qp}.config.scale.point_labels[{pi}]", p)
            for ri, r in enumerate(cfg.get("rows", [])):
                add(f"{qp}.config.rows[{ri}].label", r.get("label"))
    return found


def validate_semantics(definition: dict[str, Any], *, profile: str = "standalone") -> list[Issue]:
    issues: list[Issue] = []
    err = lambda code, path, msg: issues.append(Issue(code, path, msg, "error"))  # noqa: E731
    warn = lambda code, path, msg: issues.append(Issue(code, path, msg, "warning"))  # noqa: E731

    schema_version = definition.get("schema_version", 1)
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        err("schema_version", "$.schema_version", f"unsupported schema version {schema_version}")

    # --- languages and translation status ---------------------------------
    default_lang = definition["default_language"]
    languages = definition["languages"]
    if default_lang not in languages:
        err(
            "default_language", "$.default_language", "default_language must be listed in languages"
        )
    status = definition.get("translation_status", {})
    for lang in languages:
        if lang != default_lang and lang not in status:
            err(
                "translation_status",
                "$.translation_status",
                f"missing translation_status for '{lang}'",
            )
    for lang in status:
        if lang not in languages:
            err(
                "translation_status",
                f"$.translation_status.{lang}",
                "language not listed in languages",
            )
        elif lang == default_lang:
            warn(
                "translation_status",
                f"$.translation_status.{lang}",
                "default language needs no status",
            )
    for path, obj in _walk_i18n(definition):
        if default_lang not in obj:
            err("i18n_default", path, f"missing text for default language '{default_lang}'")
        for lang in obj:
            if lang not in languages:
                warn(
                    "i18n_extra", f"{path}.{lang}", "text for a language the survey does not offer"
                )

    # --- keys and question inventory ------------------------------------
    questions: dict[str, QuestionInfo] = {}
    section_keys: set[str] = set()
    email_questions: list[str] = []
    index = 0
    for si, section in enumerate(definition["sections"]):
        sp = f"$.sections[{si}]"
        if section["key"] in section_keys:
            err("duplicate_key", f"{sp}.key", f"duplicate section key '{section['key']}'")
        section_keys.add(section["key"])
        for qi, q in enumerate(section["questions"]):
            qp = f"{sp}.questions[{qi}]"
            if q["key"] in questions:
                err("duplicate_key", f"{qp}.key", f"duplicate question key '{q['key']}'")
                continue
            info = QuestionInfo(q["key"], index, si, section["key"], q["type"], q, qp)
            index += 1
            seen: set[str] = set()
            for oi, o in enumerate(q.get("options", [])):
                if o["key"] in seen:
                    err(
                        "duplicate_key",
                        f"{qp}.options[{oi}].key",
                        f"duplicate option key '{o['key']}'",
                    )
                seen.add(o["key"])
                info.option_keys.append(o["key"])
            questions[q["key"]] = info
            if q["type"] == "email":
                email_questions.append(q["key"])

    if len(email_questions) > 1:
        err("email_count", "$", f"at most one email question is allowed, found {email_questions}")

    # --- per-question configuration -------------------------------------
    for info in questions.values():
        q, qp, t = info.question, info.path, info.type
        cfg = q.get("config") or {}
        allowed = CONFIG_BY_TYPE.get(t, set())
        for k in cfg:
            if k not in allowed:
                warn("config_mismatch", f"{qp}.config.{k}", f"'{k}' is not used by type '{t}'")
        if t == "info" and q.get("options"):
            warn("info_options", f"{qp}.options", "info questions do not use options")
        if t != "multi":
            for oi, o in enumerate(q.get("options", [])):
                if o.get("exclusive"):
                    warn(
                        "exclusive_non_multi",
                        f"{qp}.options[{oi}].exclusive",
                        "exclusive only applies to multi",
                    )
        if t == "multi":
            mx, mn = cfg.get("max_selections"), cfg.get("min_selections")
            n = len(info.option_keys)
            if mx is not None and mx > n:
                err(
                    "max_selections",
                    f"{qp}.config.max_selections",
                    f"max_selections {mx} exceeds {n} options",
                )
            if mn is not None and mx is not None and mn > mx:
                err(
                    "min_selections",
                    f"{qp}.config.min_selections",
                    "min_selections exceeds max_selections",
                )
        if t == "ranking":
            for item in cfg.get("optional_items", []):
                if item not in info.option_keys:
                    err(
                        "optional_items",
                        f"{qp}.config.optional_items",
                        f"'{item}' is not an option",
                    )
        if scale := cfg.get("scale"):
            if scale["min"] >= scale["max"]:
                err("scale_range", f"{qp}.config.scale", "scale min must be less than max")
            pl = scale.get("point_labels")
            if pl is not None and len(pl) != scale["max"] - scale["min"] + 1:
                err(
                    "scale_labels",
                    f"{qp}.config.scale.point_labels",
                    "one label per scale point is required",
                )
        if t == "matrix":
            rows = cfg.get("rows") or []
            seen_rows: set[str] = set()
            for ri, r in enumerate(rows):
                if r["key"] in seen_rows:
                    err(
                        "duplicate_key",
                        f"{qp}.config.rows[{ri}].key",
                        f"duplicate row key '{r['key']}'",
                    )
                seen_rows.add(r["key"])
            if cfg.get("rows_from") and rows:
                err("matrix_rows", f"{qp}.config", "use either rows_from or rows, not both")
        if t == "email" and cfg.get("link_identity") and profile != "integrated":
            err(
                "link_identity",
                f"{qp}.config.link_identity",
                "link_identity requires the integrated profile",
            )
        if t == "number":
            lo, hi = cfg.get("min_value"), cfg.get("max_value")
            if lo is not None and hi is not None and lo > hi:
                err("number_range", f"{qp}.config", "min_value exceeds max_value")
        if t == "date":
            lo, hi = cfg.get("min_date"), cfg.get("max_date")
            if lo and hi and lo > hi:
                err("date_range", f"{qp}.config", "min_date exceeds max_date")

    # --- DAG rule (DEF-10) ------------------------------------------------
    def check_edge(
        path: str, source: QuestionInfo | None, target_key: str, *, section_index: int | None = None
    ):
        target = questions.get(target_key)
        if target is None:
            err("dag_unknown", path, f"references unknown question '{target_key}'")
            return None
        if source is not None:
            if target.key == source.key:
                err("dag_self", path, f"question '{source.key}' references itself")
                return None
            if target.index >= source.index:
                err(
                    "dag_forward",
                    path,
                    f"'{source.key}' may only depend on earlier questions; '{target_key}' comes later",
                )
                return None
        elif section_index is not None and target.section_index >= section_index:
            err(
                "dag_section",
                path,
                f"a section may only depend on questions in earlier sections; '{target_key}' is not",
            )
            return None
        return target

    def check_condition(path: str, cond: dict[str, Any], target: QuestionInfo | None) -> None:
        if target is None:
            return
        op = cond["op"]
        t = target.type
        if op == "answered":
            if t == "info":
                err("condition_op", path, "info questions are never answered")
            return
        if t in ("text", "number", "date", "email", "info", "matrix"):
            err("condition_op", path, f"only 'answered' can test a '{t}' question")
            return
        if op == "contains" and t not in MULTI_VALUED:
            err(
                "condition_op",
                path,
                f"'contains' requires a multi-valued question, '{target.key}' is {t}",
            )
            return
        if op in ("eq", "neq", "in") and t in MULTI_VALUED:
            err("condition_op", path, f"use 'contains' for multi-valued question '{target.key}'")
            return
        values = [cond["value"]] if "value" in cond else cond.get("values", [])
        if t == "scale":
            scale = target.question["config"]["scale"]
            for v in values:
                if not v.lstrip("-").isdigit() or not scale["min"] <= int(v) <= scale["max"]:
                    err(
                        "condition_value",
                        path,
                        f"'{v}' is outside scale {scale['min']}..{scale['max']}",
                    )
            return
        has_source = bool((target.question.get("config") or {}).get("options_source"))
        for v in values:
            if v not in target.option_keys and not has_source:
                err("condition_value", path, f"'{v}' is not an option of '{target.key}'")

    for si, section in enumerate(definition["sections"]):
        sp = f"$.sections[{si}]"
        for ci, cond in enumerate(section.get("visible_if", [])):
            cp = f"{sp}.visible_if[{ci}]"
            check_condition(cp, cond, check_edge(cp, None, cond["question"], section_index=si))
    for info in questions.values():
        qp = info.path
        for ci, cond in enumerate(info.question.get("visible_if", [])):
            cp = f"{qp}.visible_if[{ci}]"
            check_condition(cp, cond, check_edge(cp, info, cond["question"]))
        rows_from = (info.question.get("config") or {}).get("rows_from")
        if rows_from:
            target = check_edge(f"{qp}.config.rows_from", info, rows_from)
            if target is not None and target.type != "multi":
                err(
                    "rows_from_type",
                    f"{qp}.config.rows_from",
                    f"rows_from must reference a multi question, '{rows_from}' is {target.type}",
                )

    # --- reachability (warning) -----------------------------------------
    if not any(i.level == "error" for i in issues):
        unreachable: set[str] = set()
        for info in questions.values():
            conds = list(info.question.get("visible_if", []))
            conds += definition["sections"][info.section_index].get("visible_if", [])
            by_target: dict[str, list[dict[str, Any]]] = {}
            for c in conds:
                by_target.setdefault(c["question"], []).append(c)
            dead = any(c["question"] in unreachable for c in conds)
            for target_key, cs in by_target.items():
                if questions[target_key].type not in SINGLE_VALUED:
                    continue
                allowed: set[str] | None = None
                for c in cs:
                    if c["op"] == "eq":
                        s = {c["value"]}
                    elif c["op"] == "in":
                        s = set(c["values"])
                    else:
                        continue
                    allowed = s if allowed is None else allowed & s
                if allowed is not None and not allowed:
                    dead = True
            if dead:
                unreachable.add(info.key)
                warn("unreachable", info.path, f"question '{info.key}' can never be shown")

    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)
