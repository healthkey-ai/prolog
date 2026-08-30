/**
 * Apply a theme at runtime (THM-4, THM-5): CSS custom properties on :root,
 * @font-face rules, optional Google Fonts link, layout data attributes,
 * favicon, and chrome-string overrides. Idempotent; re-applying replaces.
 */
import { addStrings } from "@/i18n";
import type { Palette, Theme } from "./types";

const STYLE_ID = "prolog-theme";
const FONTS_ID = "prolog-theme-fonts";

const TOKEN_KEYS: (keyof Palette)[] = ["primary", "primary_deep", "on_primary", "secondary", "accent", "focus", "ground", "surface", "tint", "ink", "ink_soft", "line", "error", "success"];

export function paletteVariables(p: Partial<Palette>): string {
  const lines: string[] = [];
  const primaryDeep = p.primary_deep ?? p.primary;
  const values: Partial<Palette> = { ...p, primary_deep: primaryDeep, on_primary: p.on_primary ?? (p.primary ? "#ffffff" : undefined), focus: p.focus ?? p.accent };
  for (const key of TOKEN_KEYS) {
    const v = values[key];
    if (v) lines.push(`  --p-${key.replace(/_/g, "-")}: ${v};`);
  }
  return lines.join("\n");
}

export function themeCss(theme: Theme): string {
  const t = theme.typography ?? {};
  const s = theme.shape ?? {};
  const l = theme.layout ?? {};
  const root: string[] = [paletteVariables(theme.colors.light)];
  const push = (name: string, value: string | number | undefined) => {
    if (value !== undefined && value !== null && value !== "") root.push(`  --p-${name}: ${value};`);
  };
  push("font-heading", t.heading_family);
  push("font-body", t.body_family);
  push("weight-heading", t.heading_weight);
  push("weight-body", t.body_weight);
  push("tracking", t.tracking);
  push("base-size", t.base_size_px ? `${Math.max(16, t.base_size_px)}px` : undefined);
  push("radius-card", s.radius_card);
  push("radius-input", s.radius_input);
  push("radius-button", s.radius_button);
  push("radius-sheet", s.radius_sheet);
  push("shadow", s.shadow);
  push("content-max", l.content_max_width);

  const faces = (t.font_faces ?? [])
    .map(
      (f) =>
        `@font-face { font-family: ${JSON.stringify(f.family)}; src: url(${JSON.stringify(f.src)}) format(${JSON.stringify(formatOf(f.src))}); font-weight: ${f.weight ?? "400"}; font-style: ${f.style ?? "normal"}; font-display: ${f.display ?? "swap"}; }`,
    )
    .join("\n");

  const dark =
    theme.color_scheme === "light-dark" && theme.colors.dark
      ? `@media (prefers-color-scheme: dark) {\n:root {\n${paletteVariables(theme.colors.dark)}\n}\n}`
      : "";
  const motion = theme.motion?.enabled === false ? `*, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }` : "";
  return `${faces}\n:root {\n${root.join("\n")}\n}\n${dark}\n${motion}`.trim();
}

function formatOf(src: string): string {
  const ext = src.split("?")[0].split(".").pop()?.toLowerCase();
  return ext === "woff2" ? "woff2" : ext === "woff" ? "woff" : ext === "otf" ? "opentype" : "truetype";
}

export function applyTheme(theme: Theme, doc: Document = document): void {
  let style = doc.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!style) {
    style = doc.createElement("style");
    style.id = STYLE_ID;
    doc.head.appendChild(style);
  }
  style.textContent = themeCss(theme);

  const existingFonts = doc.getElementById(FONTS_ID);
  const families = theme.typography?.google_fonts ?? [];
  if (families.length) {
    const href = `https://fonts.googleapis.com/css2?${families.map((f) => `family=${encodeURIComponent(f).replace(/%3A/g, ":").replace(/%3B/g, ";").replace(/%40/g, "@").replace(/%20/g, "+")}`).join("&")}&display=swap`;
    let link = existingFonts as HTMLLinkElement | null;
    if (!link) {
      link = doc.createElement("link");
      link.id = FONTS_ID;
      link.rel = "stylesheet";
      doc.head.appendChild(link);
    }
    link.href = href;
  } else {
    existingFonts?.remove();
  }

  const root = doc.documentElement;
  root.dataset.theme = theme.code;
  root.dataset.align = theme.layout?.copy_alignment ?? "left";
  root.dataset.logo = theme.layout?.logo_placement ?? "top-left";
  root.style.colorScheme = theme.color_scheme === "light-dark" ? "light dark" : "light";
  let meta = doc.querySelector<HTMLMetaElement>('meta[name="color-scheme"]');
  if (!meta) {
    meta = doc.createElement("meta");
    meta.name = "color-scheme";
    doc.head.appendChild(meta);
  }
  meta.content = theme.color_scheme === "light-dark" ? "light dark" : "light";

  if (theme.assets?.favicon) {
    let icon = doc.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!icon) {
      icon = doc.createElement("link");
      icon.rel = "icon";
      doc.head.appendChild(icon);
    }
    icon.href = theme.assets.favicon;
  }

  if (theme.strings) addStrings(theme.strings);
}
