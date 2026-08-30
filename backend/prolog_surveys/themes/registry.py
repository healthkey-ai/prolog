"""Theme discovery, validation and lookup (THM-1, THM-2, THM-3, THM-7, THM-8)."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import conf
from ..definitions.schema import Issue, theme_schema, validate_against
from ..definitions.validate import has_errors
from .contrast import palette_warnings

log = logging.getLogger(__name__)

DEFAULT_THEME = "default"
ASSET_EXTENSIONS = {
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
}
ASSET_KEYS = ("logo", "logo_on_primary", "favicon")


@dataclass
class Theme:
    code: str
    directory: Path
    data: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    _public: dict[str, Any] | None = field(default=None, repr=False, compare=False)

    def asset_path(self, relative: str) -> Path | None:
        """Resolve an asset inside the theme directory; None if outside or disallowed."""
        if not relative or "\x00" in relative or relative.startswith(("/", "\\")):
            return None
        try:
            candidate = (self.directory / relative).resolve()
            candidate.relative_to(self.directory.resolve())
            if candidate.suffix.lower() not in ASSET_EXTENSIONS or not candidate.is_file():
                return None
        except (ValueError, OSError):
            # Outside the directory, or a path the OS refuses (embedded NUL, too
            # long, ...): not an asset, never a server error.
            return None
        return candidate

    def asset_references(self) -> list[str]:
        assets = self.data.get("assets", {})
        refs = [assets[k] for k in ASSET_KEYS if assets.get(k)]
        refs += list(assets.get("decor", []))
        refs += [f["src"] for f in self.data.get("typography", {}).get("font_faces", [])]
        return refs

    def public(self, asset_path: Callable[[str], str], absolute: Callable[[str], str]) -> dict:
        """Theme document for the runner with asset references rewritten.

        ``asset_path`` maps a theme-relative asset to its host-independent URL
        path (computed once per theme); ``absolute`` prefixes the requesting
        host's scheme and origin, which is all that varies per request.
        """
        if self._public is None:
            doc = json.loads(json.dumps(self.data))
            doc.pop("$schema", None)
            assets = doc.get("assets", {})
            for k in ASSET_KEYS:
                if assets.get(k):
                    assets[k] = asset_path(assets[k])
            if assets.get("decor"):
                assets["decor"] = [asset_path(a) for a in assets["decor"]]
            for face in doc.get("typography", {}).get("font_faces", []):
                face["src"] = asset_path(face["src"])
            self._public = doc
        doc = dict(self._public)
        if "assets" in doc:
            assets = dict(doc["assets"])
            for k in ASSET_KEYS:
                if assets.get(k):
                    assets[k] = absolute(assets[k])
            if assets.get("decor"):
                assets["decor"] = [absolute(a) for a in assets["decor"]]
            doc["assets"] = assets
        if doc.get("typography", {}).get("font_faces"):
            typography = dict(doc["typography"])
            typography["font_faces"] = [
                {**face, "src": absolute(face["src"])} for face in typography["font_faces"]
            ]
            doc["typography"] = typography
        return doc


def validate_theme(directory: Path) -> tuple[dict[str, Any], list[Issue]]:
    """Schema + asset + contrast validation of ``directory/theme.json``."""
    path = directory / "theme.json"
    if not path.is_file():
        return {}, [Issue("missing", "$", f"{path} not found")]
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [Issue("json", "$", f"{path}: {exc}")]
    issues = validate_against(theme_schema(), data)
    if has_errors(issues):
        return data, issues
    theme = Theme(code=data["code"], directory=directory, data=data)
    for ref in theme.asset_references():
        if theme.asset_path(ref) is None:
            issues.append(
                Issue(
                    "asset",
                    "$.assets",
                    f"asset '{ref}' is missing, outside the theme directory, or has a disallowed type",
                )
            )
    colors = data.get("colors", {})
    light_warnings = palette_warnings(colors.get("light", {}))
    for warning in light_warnings:
        issues.append(Issue("contrast", "$.colors.light", warning, "warning"))
    if "dark" in colors:
        # The runner overrides the light tokens with the dark ones, so what a
        # dark-mode participant sees is light ∪ dark; a partial dark palette
        # checked alone would skip every pair it does not fully redefine.
        effective = {**colors.get("light", {}), **colors["dark"]}
        for warning in palette_warnings(effective):
            if warning not in light_warnings:
                issues.append(Issue("contrast", "$.colors.dark", warning, "warning"))
    if data.get("color_scheme") == "light-dark" and "dark" not in data.get("colors", {}):
        issues.append(
            Issue("dark", "$.colors", "light-dark themes should define colors.dark", "warning")
        )
    return data, issues


class ThemeRegistry:
    def __init__(self) -> None:
        self._themes: dict[str, Theme] | None = None
        self._lock = threading.Lock()
        # Unknown codes already logged: a misconfigured survey is resolved on
        # every definition request, and one line per code is enough.
        self._warned: set[str] = set()

    def reload(self) -> dict[str, Theme]:
        themes: dict[str, Theme] = {}
        for root in (Path(p) for p in conf.get("PROLOG_THEME_DIRS")):
            if not root.is_dir():
                log.warning("theme directory does not exist: %s", root)
                continue
            for directory in sorted(p for p in root.iterdir() if p.is_dir()):
                if not (directory / "theme.json").is_file():
                    continue
                data, issues = validate_theme(directory)
                if has_errors(issues):
                    errors = [i for i in issues if i.level == "error"]
                    log.error("theme %s rejected: %s", directory, "; ".join(map(str, errors)))
                    continue
                warnings = [i.message for i in issues if i.level == "warning"]
                for w in warnings:
                    log.warning("theme %s: %s", data["code"], w)
                if data["code"] in themes:
                    log.warning(
                        "theme code %s defined twice; keeping %s",
                        data["code"],
                        themes[data["code"]].directory,
                    )
                    continue
                themes[data["code"]] = Theme(
                    code=data["code"], directory=directory, data=data, warnings=warnings
                )
        if DEFAULT_THEME not in themes:
            log.error("no '%s' theme found in PROLOG_THEME_DIRS", DEFAULT_THEME)
        with self._lock:
            self._themes = themes
            self._warned = set()
        return themes

    def all(self) -> dict[str, Theme]:
        if self._themes is None:
            self.reload()
        return self._themes or {}

    def get(self, code: str | None) -> Theme | None:
        return self.all().get(code or DEFAULT_THEME)

    def resolve(self, code: str | None) -> Theme | None:
        """Theme for ``code`` or the default, logging unknown codes (THM-3)."""
        themes = self.all()
        if code and code in themes:
            return themes[code]
        if code and code != DEFAULT_THEME and code not in self._warned:
            self._warned.add(code)
            log.warning("unknown theme code '%s'; falling back to %s", code, DEFAULT_THEME)
        return themes.get(DEFAULT_THEME)


registry = ThemeRegistry()
