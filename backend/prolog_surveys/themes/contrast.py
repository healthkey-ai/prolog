"""WCAG 2.x contrast helpers for theme registration (THM-8)."""

from __future__ import annotations

import re

HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_hex(color: str) -> tuple[float, float, float] | None:
    m = HEX_RE.match(color.strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _channel(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float | None:
    """Ratio between two hex colours, or None if either is not plain hex."""
    ca, cb = parse_hex(a), parse_hex(b)
    if ca is None or cb is None:
        return None
    la, lb = luminance(ca), luminance(cb)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# (foreground, background, minimum) pairs checked on every palette.
CHECKS: list[tuple[str, str, float]] = [
    ("ink", "surface", 4.5),
    ("ink", "ground", 4.5),
    ("ink_soft", "surface", 4.5),
    ("ink_soft", "ground", 4.5),
    ("ink", "tint", 4.5),
    ("primary", "surface", 4.5),
    ("on_primary", "primary", 4.5),
    ("error", "surface", 4.5),
    ("success", "surface", 4.5),
]


def palette_warnings(palette: dict[str, str]) -> list[str]:
    colors = {**palette}
    colors.setdefault("on_primary", "#ffffff")
    out = []
    for fg, bg, minimum in CHECKS:
        if fg not in colors or bg not in colors:
            continue
        ratio = contrast_ratio(colors[fg], colors[bg])
        if ratio is None:
            continue
        if ratio < minimum:
            out.append(f"{fg} on {bg} is {ratio:.2f}:1, below {minimum}:1")
    return out
