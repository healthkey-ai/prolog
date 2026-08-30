# Theme manual

**Contract:** [`schema/theme.schema.json`](../../schema/theme.schema.json) (JSON Schema 2020-12, `schema_version` 1)  
**Built-in themes:** [`themes/default`](../../themes/default) (neutral) · [`themes/contrast`](../../themes/contrast) (high contrast, light-dark, larger type, motion off)  
**Requirements:** THM-1…THM-8 in [requirements.md](../requirements.md).

A theme restyles the participant runner for one customer or programme
**at runtime**: the runner is built once, brand-free, and applies a theme by
setting CSS custom properties, declaring `@font-face` rules and switching a
few layout flags. A survey selects a theme by code; themes live outside this
repository (a customer's private repository) and are mounted at deployment.
Changing a theme never requires a rebuild.

---

## 1. Theme directory

```
my-theme/
├── theme.json              # the document described below (required)
├── logo.svg                # logo for light surfaces: wizard header, non-immersive intro
├── logo-on-primary.svg     # logo for the primary-colour ground: immersive intro/completion
├── favicon.svg
├── decor/blob-1.svg …      # up to three decorative shapes for immersive screens
└── fonts/*.woff2           # self-hosted faces referenced by typography.font_faces
```

Asset paths in `theme.json` are relative to the directory. Allowed asset
types: `.svg .png .jpg .jpeg .webp .ico .woff .woff2 .ttf .otf`. Nothing
else in the directory is served.

---

## 2. `theme.json` reference

```jsonc
{
  "schema_version": 1,
  "code": "acme",                      // ^[a-z0-9][a-z0-9-]*$ — referenced by a definition's "theme"
  "name": "ACME Patient Programmes",   // shown as the logo's alt text
  "version": "1.0.0",
  "color_scheme": "light",             // light | light-dark
  "colors": { "light": { … }, "dark": { … } },
  "typography": { … },
  "shape": { … },
  "layout": { … },
  "assets": { … },
  "motion": { "enabled": true },
  "strings": { … }
}
```

### 2.1 `colors`

`colors.light` is required and must contain every token below except the
three marked *derived*. `colors.dark` (any subset) is used only when
`color_scheme` is `light-dark`, under `prefers-color-scheme: dark`.

| Token | Required | Used for |
| --- | --- | --- |
| `primary` | yes | Primary buttons, selected borders and fills, the immersive ground of intro/completion screens |
| `primary_deep` | derived (= `primary`) | Hover/pressed state of primary buttons |
| `on_primary` | derived (= `#ffffff`) | Text and icons on `primary` |
| `secondary` | yes | Decorative shapes and large display elements — **never small text** |
| `accent` | yes | Progress-bar fill, decorative shapes — **never text** |
| `focus` | derived (= `accent`) | Focus rings on every interactive element |
| `ground` | yes | Page background of question screens |
| `surface` | yes | Cards, inputs, header/footer bars, sheets |
| `tint` | yes | Selected/hover fill of option cards, progress track, info panels, chips |
| `ink` | yes | Body text, question headings |
| `ink_soft` | yes | Help text, captions, section labels, saved indicator |
| `line` | yes | Borders and dividers |
| `error` | yes | Validation and save-failure messages |
| `success` | yes | "Saved" and completion confirmations |

Values are CSS colours; use 6-digit hex so the contrast check can run.

### 2.2 `typography`

| Key | Meaning |
| --- | --- |
| `heading_family`, `body_family` | CSS font-family stacks for headings/question text/buttons and for body copy. Always end with real fallbacks (`"Helvetica Neue", Arial, sans-serif`). |
| `heading_weight`, `body_weight` | 100–900. |
| `tracking` | Global letter-spacing, e.g. `"0.02em"`. |
| `base_size_px` | Body size in px; values below 16 are clamped to 16 by the runner. |
| `font_faces` | Self-hosted faces: `[{ "family", "src": "fonts/x.woff2", "weight": "400 700", "style": "normal", "display": "swap" }]`. The runner injects one `@font-face` per entry; `src` must be an asset in the theme directory. |
| `google_fonts` | Families to load from Google Fonts, e.g. `["Hanken Grotesk:wght@400;500;700"]`. Loads a stylesheet from `fonts.googleapis.com`; only use where third-party font loading is acceptable, and list the family in the stacks above. |

### 2.3 `shape`

| Key | Default in `default` theme | Applies to |
| --- | --- | --- |
| `radius_card` | `12px` | Option cards, matrix rows, ranking items, interstitial |
| `radius_input` | `8px` | Inputs, combobox trigger, scale segments, popovers |
| `radius_button` | `8px` | Buttons (`999px` for pills) |
| `radius_sheet` | `16px` | The "All questions" sheet |
| `shadow` | `0 2px 12px …` | Sticky footer and sheet |

### 2.4 `layout`

| Key | Meaning |
| --- | --- |
| `copy_alignment` | `left` (default) or `center` for headings and main copy. |
| `content_max_width` | Width of the reading column, default `640px`. |
| `immersive_intro` | `true`: intro and completion screens use `primary` as a full-bleed ground with the on-primary logo and decorative shapes; `false`: same light surface as question screens. |
| `logo_placement` | `top-left` (default) or `top-right` on intro/completion screens. |

### 2.5 `assets`

| Key | Meaning |
| --- | --- |
| `logo` | Logo for light surfaces (SVG preferred); shown in the wizard header and on non-immersive intro/completion. |
| `logo_on_primary` | Variant for the primary ground; falls back to `logo`. |
| `favicon` | Browser tab icon. |
| `decor` | Up to three SVGs placed on immersive screens (`aria-hidden`), hugging the right edge and corners so they never sit behind left-aligned copy. Keep them free of embedded fonts/rasters. |

### 2.6 `motion`

`{"enabled": false}` disables transitions regardless of user preference.
`prefers-reduced-motion` is always honoured.

### 2.7 `strings` — chrome overrides

Overrides for the runner's own UI strings, per key then language. Survey
content (questions, options, intro, completion) is never affected — it comes
from the definition.

```json
"strings": {
  "intro.start":    { "en": "Start the survey", "es": "Comenzar la encuesta" },
  "complete.title": { "en": "Thank you — your voice matters" }
}
```

Keys available (the runner ships en, es, fr, pt; a theme may add any other
language it offers):

| Area | Keys |
| --- | --- |
| App | `app.title` `app.loading` `app.error` `app.retry` `app.notFound` |
| Intro | `intro.eyebrow` `intro.minutes` (`{{count}}`) `intro.anonymous` `intro.language` `intro.start` `intro.continue` `intro.welcomeBack` `intro.resumeHint` `intro.startAgain` `intro.startAgainConfirm` `intro.startNew` `intro.consentAgree` `intro.consentRequired` `intro.submitted` |
| Header | `header.section` (`{{number}}`, `{{total}}`) `header.overview` `header.language` `header.progress` |
| Question | `question.eyebrow` (`{{number}}`, `{{total}}`) `question.optional` `question.info` |
| Footer | `nav.back` `nav.next` `nav.finish` `nav.saving` `nav.saved` `nav.saveFailed` |
| Skip prompt | `skip.prompt` `skip.skip` `skip.answer` `skip.hard` |
| Overview | `overview.title` `overview.close` `overview.answered` `overview.skipped` `overview.current` `overview.unanswered` `overview.unreachable` `overview.noAnswer` |
| Interstitial | `interstitial.eyebrow` (`{{number}}`) `interstitial.continue` |
| Controls | `single.other` `dropdown.placeholder` `dropdown.noResults` `dropdown.clear` `text.remaining` (`{{count}}`) `number.placeholder` `multi.counter` (`{{count}}`, `{{max}}`) `multi.limit` (`{{max}}`) `matrix.legend` `matrix.incomplete` |
| Ranking | `ranking.help` `ranking.moveUp` `ranking.moveDown` (`{{label}}`) `ranking.position` (`{{label}}`, `{{position}}`, `{{total}}`) `ranking.optional` `ranking.include` `ranking.exclude` |
| Email step | `email.placeholder` `email.save` `email.skip` `email.saved` `email.invalid` |
| Completion | `complete.eyebrow` `complete.title` `complete.body` `complete.readonly` `complete.missing` |

Keep the same `{{placeholders}}` as the default string.

---

## 3. Rules enforced at registration

`manage.py register_theme path/to/my-theme` (also run automatically when the
theme directories are scanned) checks:

- `theme.json` validates against the schema.
- Every referenced asset exists inside the theme directory and has an
  allowed type; paths escaping the directory are rejected.
- **Contrast** (WCAG 2.x): `ink` / `ink_soft` / `primary` / `error` /
  `success` on `surface` and `ground`, `ink` on `tint`, and `on_primary` on
  `primary` must reach 4.5:1 — anything lower is a **warning** (logged, and
  returned in the theme API's `warnings`). A `light-dark` theme without
  `colors.dark` is warned.
- Duplicate codes: the first directory wins, the second is logged.

Errors reject the theme (it is not registered); warnings keep it usable but
must be addressed before a launch.

Independently of the theme, the runner never uses `secondary` or `accent`
for small text, keeps body text ≥ 16 px, ≥ 44 px targets and visible focus
rings.

---

## 4. Mounting and selecting a theme

```
PROLOG_THEME_DIRS=/app/themes:/data/themes      # path-separated list of parent directories
```

Every subdirectory containing a `theme.json` is registered under its
`code`. In the container image `/app/themes` holds the built-in themes and
`/data/themes` is the customer mount (`docker-compose.yml`). Themes are
registered at first use; restart the app after adding or changing one.

A survey selects its theme in the definition: `"theme": "acme"`. An unknown
or missing code falls back to `default` with a logged warning (THM-3), so a
deployment with a missing mount degrades to the neutral look rather than
failing.

---

## 5. How the runner applies a theme

1. The runner asks for the survey definition; the response carries the
   resolved `theme_code`.
2. It fetches `GET /api/run/themes/{code}/` — the theme document with asset
   paths rewritten to absolute URLs and any registration `warnings`.
3. Before the first survey screen renders it:
   - sets every design token as a CSS custom property on `:root`
     (`--p-primary`, `--p-ground`, `--p-radius-button`, `--p-font-heading`,
     …), with fallbacks derived for `primary_deep`, `on_primary`, `focus`;
   - injects `@font-face` rules for `font_faces` and, if present, a Google
     Fonts stylesheet link;
   - adds a `prefers-color-scheme: dark` block from `colors.dark` for
     `light-dark` themes and sets `color-scheme` accordingly;
   - sets `data-theme`, `data-align`, `data-logo` on the root element for the
     layout switches, the favicon, and a motion override when
     `motion.enabled` is `false`;
   - merges `strings` into the runner's translation resources (the base
     strings are restored first, so one theme's overrides never leak into
     another survey opened later in the same session).

Every runner component references tokens only; shadcn/ui's semantic
variables (`--background`, `--card`, `--primary`, `--muted`, `--ring`,
`--radius`, …) are mapped onto the same tokens, so the whole component
library follows the theme.

Assets are served from `GET /api/run/themes/{code}/assets/{path}` with a
one-year immutable cache; change a file's name (or the theme `version` in a
new directory) when replacing artwork.

---

## 6. Authoring checklist

1. Start from `themes/default/theme.json`; change `code`, `name`, colours.
2. Check contrast as you go — `register_theme` prints the failing pairs.
3. Add the logo in both variants and a favicon (SVG).
4. Fonts: put a free fallback in the family stacks now; add licensed files to
   `fonts/` and `font_faces` when available — no other change is needed.
5. Decide `immersive_intro`, `logo_placement`, `copy_alignment`.
6. Add 2–3 decorative shapes if the brand uses them; keep them off the copy.
7. Override only the chrome strings the brand genuinely words differently.
8. Mount the directory, restart, open `/s/<slug>` on a phone and a desktop.

---

## 7. Minimal example

```json
{
  "schema_version": 1,
  "code": "acme",
  "name": "ACME",
  "color_scheme": "light",
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

The [`contrast`](../../themes/contrast/theme.json) theme shows a `light-dark`
palette, a self-hosted-free system font stack, square radii and motion off.
