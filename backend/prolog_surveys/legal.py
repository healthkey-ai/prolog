"""Deployment-supplied legal pages, served by the runner under its own theme.

Any instrument that asks a respondent for anything needs a privacy notice, and
needs it reachable *from inside the survey* — from the intro, and from the
question that asks for an email address, which is exactly where somebody
decides whether to hand one over. Sending them to another origin mid-survey, in
another site's styling, is the worst moment to do it.

The mechanism is here; the content is the deployment's, mounted the way
definitions and themes are (DEP-3):

    PROLOG_LEGAL_DIRS=/data/legal

    /data/legal/privacy.md        the default language
    /data/legal/privacy.es.md     optional per-language variants
    /data/legal/terms.md          the same mechanism for anything else

PROlog ships no policy text, no template and no placeholder wording, and takes
no view on what a notice should say. A deployment that configures nothing has
no pages: the endpoint 404s and the runner renders no link, so nobody is forced
into a page they do not have.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import conf

#: A page name is a file stem: lowercase letters, digits and hyphens. Anything
#: else — a dot, a slash, "..'' — never reaches the filesystem, so a request
#: cannot walk out of the configured directory.
PAGE_NAME = re.compile(r"^[a-z0-9-]+$")

#: Same shape as a definition's language tags.
LANGUAGE = re.compile(r"^[a-z]{2}(-[a-z0-9]+)*$", re.IGNORECASE)

MAX_BYTES = 512 * 1024


@dataclass(frozen=True, slots=True)
class LegalPage:
    """One page's Markdown, and the language it was actually found in."""

    name: str
    language: str
    markdown: str


def _roots() -> list[Path]:
    return [Path(p) for p in conf.get("PROLOG_LEGAL_DIRS")]


def available() -> set[str]:
    """Page names a deployment has mounted, in any language.

    The runner asks so it can decide whether to render a link at all — a link
    to a 404 is worse than no link, and worst on the consent screen.
    """
    names: set[str] = set()
    for root in _roots():
        if not root.is_dir():
            continue
        for path in root.glob("*.md"):
            name = path.stem.split(".")[0]
            if PAGE_NAME.match(name):
                names.add(name)
    return names


def find(name: str, language: str | None = None) -> LegalPage | None:
    """The page in ``language``, falling back to the language-less file.

    The fallback is DEF-5's rule for survey content: a respondent reading a
    language whose notice has not been translated gets the default one rather
    than nothing. Returns None when the deployment has no such page.
    """
    if not PAGE_NAME.match(name or ""):
        return None
    if language is not None and not LANGUAGE.match(language):
        language = None

    for root in _roots():
        if not root.is_dir():
            continue
        candidates = []
        if language:
            candidates.append((language, root / f"{name}.{language}.md"))
            base = language.split("-")[0]
            if base != language:
                candidates.append((base, root / f"{name}.{base}.md"))
        candidates.append(("", root / f"{name}.md"))
        for found_language, path in candidates:
            if not path.is_file():
                continue
            # A page is a document, not a download: a file large enough to be a
            # mistake is refused rather than streamed to every respondent.
            if path.stat().st_size > MAX_BYTES:
                continue
            return LegalPage(
                name=name,
                language=found_language or "",
                markdown=path.read_text(encoding="utf-8"),
            )
    return None
