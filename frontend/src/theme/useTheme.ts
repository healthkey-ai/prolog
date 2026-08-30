import type { ReactNode } from "react";

/**
 * Theme hooks. Phase 3 ships the neutral defaults; Phase 5 replaces these with
 * values loaded from the theme API without touching the pages.
 */
export function useThemeLayout(): { immersiveIntro: boolean; copyAlignment: "left" | "center"; logoPlacement: "top-left" | "top-right" } {
  return { immersiveIntro: false, copyAlignment: "left", logoPlacement: "top-left" };
}

export function useThemeLogo(): ReactNode {
  return null;
}
