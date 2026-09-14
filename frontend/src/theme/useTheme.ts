import { createElement, type ReactNode } from "react";
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
  // On the intro the theme's height is a ceiling, not a demand: a short
  // viewport (a phone) gives the logo a tenth of its height and keeps the
  // rest for the words the respondent came for.
  const height = screen === "intro" ? `min(${theme?.layout?.intro_logo_height ?? headerHeight}, 10dvh)` : headerHeight;
  return createElement("img", { src, alt: theme?.name ?? "", className: "w-auto shrink-0", style: { height }, "data-testid": "theme-logo" });
}

export function useThemeDecor(): string[] {
  const { theme } = useThemeContext();
  return theme?.assets?.decor ?? [];
}
