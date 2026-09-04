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

/** Logo for light surfaces (header) or for the primary ground (immersive screens). */
export function useThemeLogo(onPrimary = false): ReactNode {
  const { theme } = useThemeContext();
  const src = onPrimary ? (theme?.assets?.logo_on_primary ?? theme?.assets?.logo) : theme?.assets?.logo;
  if (!src) return null;
  return createElement("img", { src, alt: theme?.name ?? "", className: "h-8 w-auto shrink-0", "data-testid": "theme-logo" });
}

export function useThemeDecor(): string[] {
  const { theme } = useThemeContext();
  return theme?.assets?.decor ?? [];
}
