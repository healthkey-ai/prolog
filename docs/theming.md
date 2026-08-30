# Theming the runner

**Requirements:** THM-1…THM-8 in [requirements.md](requirements.md). **Contract:** [`schema/theme.schema.json`](../schema/theme.schema.json). **Built-in themes:** [`themes/default`](../themes/default) (neutral), [`themes/contrast`](../themes/contrast) (high contrast, light-dark).

A theme is a directory with a `theme.json` and its assets. The runner is
built once, brand-free; a theme is fetched at load time and applied by
setting CSS custom properties, injecting `@font-face` rules and toggling
layout flags. Changing a theme never requires a rebuild.

## Authoring a theme

```
my-theme/
├── theme.json            # conforms to schema/theme.schema.json
├── logo.svg              # logo for light surfaces (header, non-immersive intro)
├── logo-on-primary.svg   # logo for the primary-colour ground (immersive intro/completion)
├── favicon.svg
├── decor/blob-1.svg …    # up to three decorative shapes for immersive screens (aria-hidden)
└── fonts/*.woff2         # self-hosted faces referenced by typography.font_faces
```

Minimal `theme.json`:

```jsonc
{
  "schema_version": 1,
  "code": "acme",                         // referenced by a survey definition's "theme"
  "name": "ACME",
  "color_scheme": "light",                // or "light-dark" with colors.dark
  "colors": {
    "light": {
      "primary": "#4a1a7a", "primary_deep": "#36125a", "on_primary": "#ffffff",
      "secondary": "#7a4fb0", "accent": "#a0a2f0", "focus": "#a0a2f0",
      "ground": "#f7f5fb", "surface": "#ffffff", "tint": "#f1ecf8",
      "ink": "#241b2e", "ink_soft": "#5f5570", "line": "#e3dcee",
      "error": "#b42318", "success": "#067647"
    }
  },
  "typography": {
    "heading_family": "\"Brand Sans\", \"Helvetica Neue\", Arial, sans-serif",
    "body_family": "\"Brand Sans\", \"Helvetica Neue\", Arial, sans-serif",
    "heading_weight": 500, "tracking": "0.02em", "base_size_px": 17,
    "font_faces": [{ "family": "Brand Sans", "src": "fonts/brand-sans.woff2", "weight": "400 700" }]
  },
  "shape": { "radius_card": "12px", "radius_input": "12px", "radius_button": "999px", "radius_sheet": "20px" },
  "layout": { "copy_alignment": "left", "content_max_width": "640px", "immersive_intro": true, "logo_placement": "top-right" },
  "assets": { "logo": "logo.svg", "logo_on_primary": "logo-on-primary.svg", "favicon": "favicon.svg", "decor": ["decor/blob-1.svg", "decor/blob-2.svg"] },
  "strings": { "intro.start": { "en": "Start the survey" } }
}
```

### Token roles

| Token | Used for |
| --- | --- |
| `primary` / `primary_deep` / `on_primary` | primary buttons, selected borders, question headings' accents, immersive grounds |
| `secondary` | decorative shapes only — **never small text** |
| `accent` | progress fill, decorative shapes — **never text** |
| `focus` | focus rings (defaults to `accent`) |
| `ground` / `surface` / `tint` | app background / cards and inputs / selected-hover fill and progress track |
| `ink` / `ink_soft` / `line` | body text / help text and captions / borders |
| `error` / `success` | validation and saved states |

### Rules enforced at registration (THM-7, THM-8)

- `theme.json` must validate against the schema.
- Every referenced asset must exist inside the theme directory and be an
  image or font (`.svg .png .jpg .webp .ico .woff .woff2 .ttf .otf`).
- Contrast is checked for `ink`/`ink_soft`/`primary`/`error`/`success` on
  `surface`/`ground`/`tint` and `on_primary` on `primary`; anything below
  4.5:1 is logged as a warning and returned in the theme API's `warnings`.
- `base_size_px` below 16 is clamped to 16 by the runner.
- Small text in components never uses `secondary` or `accent`, regardless
  of theme.

Validate locally: `manage.py register_theme path/to/my-theme`.

## Mounting a theme

Add the parent directory to `PROLOG_THEME_DIRS` (path-separator list) and
restart. Each subdirectory with a `theme.json` is registered under its
`code`. A survey selects a theme with `"theme": "acme"` in its definition;
unknown codes fall back to `default` with a logged warning (THM-3).

```
PROLOG_THEME_DIRS=/app/themes:/data/themes
```

In the container image `/app/themes` holds the built-in themes and
`/data/themes` is the customer mount (see `docker-compose.yml`).

## Runtime behaviour

- `GET /api/run/themes/{code}/` returns the theme with asset paths rewritten
  to absolute URLs; `GET /api/run/themes/{code}/assets/{path}` serves assets
  with a one-year immutable cache and path-traversal protection.
- The runner reads `theme_code` from the survey definition endpoint, loads
  the theme, applies it, then renders — no flash of the default theme.
- `light-dark` themes add a `prefers-color-scheme: dark` block from
  `colors.dark`; `light` themes ignore the OS preference (THM-5).
- `strings` merges into the runner's i18next resources per language and can
  only override chrome strings; survey content is never affected (THM-6).
- `motion.enabled: false` disables transitions; `prefers-reduced-motion` is
  always honoured.

## Licensed fonts

Put the licensed `.woff2` files in the theme directory and reference them
from `typography.font_faces`; they are served from the customer mount and
never enter this repository. Until they are available, list a free
fallback in the family stack (and optionally `google_fonts`), then swap by
editing only `theme.json`.
