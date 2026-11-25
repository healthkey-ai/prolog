import { createElement, type ReactNode } from "react";
import { httpUrl } from "@/pages/httpUrl";
import { useThemeContext } from "./ThemeProvider";

export interface ThemeLayout {
  immersiveIntro: boolean;
  logoPlacement: "top-left" | "top-right";
}

export function useThemeLayout(): ThemeLayout {
  const { theme } = useThemeContext();
  return {
    immersiveIntro: theme?.layout?.immersive_intro ?? false,
    logoPlacement: theme?.layout?.logo_placement ?? "top-left",
  };
}

/**
 * Logo for light surfaces (header) or for the primary ground (immersive
 * screens). The theme decides how tall it is: a plain symbol reads at 2rem, a
 * wordmark or a mark with text inside it does not, and the intro has room the
 * header lacks (`layout.logo_height`, `layout.intro_logo_height`).
 */
export function useThemeLogo(onPrimary = false, screen: "header" | "intro" = "header"): ReactNode {
  const { theme } = useThemeContext();
  const src = onPrimary ? (theme?.assets?.logo_on_primary ?? theme?.assets?.logo) : theme?.assets?.logo;
  if (!src) return null;
  const headerHeight = theme?.layout?.logo_height ?? "2rem";
  // On the intro the theme's height is the height: a mark with text in it
  // is sized so that text can be read, and shrinking it on a short viewport
  // defeats that. The intro floats a top-right logo above the column, so the
  // size costs the words nothing.
  const height = screen === "intro" ? (theme?.layout?.intro_logo_height ?? headerHeight) : headerHeight;
  // In the header a wide logo gives way (scaled, not cropped) so the section
  // title and the controls beside it still fit a 320px screen.
  const fit = screen === "header" ? "max-w-[30vw] object-contain object-left" : "";
  return createElement("img", { src, alt: theme?.name ?? "", className: `w-auto shrink-0 ${fit}`.trim(), style: { height }, "data-testid": "theme-logo" });
}

/**
 * The theme's `exit_url` when it is safe to follow, as the schema allows it: a
 * path on this site or an http(s) URL, with no whitespace, control character
 * or backslash anywhere (a browser drops a tab or newline from a URL, so
 * `/<tab>/host` would leave the site). A path must still be on this site once
 * the browser has read it. A theme served from elsewhere is checked here again.
 */
export function exitUrl(raw: string | undefined): string | undefined {
  // eslint-disable-next-line no-control-regex
  if (!raw || /[\u0000-\u0020\u007f\\]/.test(raw)) return undefined;
  if (raw.startsWith("/")) {
    if (raw.startsWith("//")) return undefined;
    try {
      const url = new URL(raw, window.location.origin);
      return url.origin === window.location.origin ? url.pathname + url.search + url.hash : undefined;
    } catch {
      return undefined;
    }
  }
  return /^https?:\/\//.test(raw) ? httpUrl(raw) : undefined;
}

export function useThemeExit(): string | undefined {
  const { theme } = useThemeContext();
  return exitUrl(theme?.exit_url);
}

export function useThemeDecor(): string[] {
  const { theme } = useThemeContext();
  return theme?.assets?.decor ?? [];
}
