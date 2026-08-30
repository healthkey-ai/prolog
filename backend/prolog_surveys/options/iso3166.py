"""Built-in option source: ISO 3166-1 countries, localised via pycountry's gettext catalogues."""

from __future__ import annotations

import gettext
from functools import lru_cache

import pycountry

SOURCE_KEY = "iso3166_countries"


@lru_cache(maxsize=32)
def countries(lang: str) -> list[dict[str, str]]:
    # gettext expands POSIX locale names only: ``pt_BR`` finds the regional
    # catalogue and falls back to ``pt``, whereas the BCP 47 form ``pt-BR``
    # matches nothing and silently yields English.
    try:
        translation = gettext.translation(
            "iso3166-1", pycountry.LOCALES_DIR, languages=[lang.replace("-", "_")], fallback=True
        )
    except OSError:  # pragma: no cover
        translation = gettext.NullTranslations()
    items = []
    for c in pycountry.countries:
        name = getattr(c, "common_name", None) or c.name
        items.append({"key": c.alpha_2, "label": translation.gettext(name)})
    items.sort(key=lambda i: i["label"].casefold())
    return items


@lru_cache(maxsize=1)
def country_keys() -> frozenset[str]:
    return frozenset(c.alpha_2 for c in pycountry.countries)


SOURCES = {SOURCE_KEY: countries}
SOURCE_KEYS = {SOURCE_KEY: country_keys}
