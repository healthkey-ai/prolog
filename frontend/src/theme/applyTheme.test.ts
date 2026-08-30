import { describe, expect, it } from "vitest";
import i18n from "@/i18n";
import { applyTheme, themeCss } from "./applyTheme";
import type { Theme } from "./types";

const theme: Theme = {
  code: "test",
  name: "Test",
  color_scheme: "light-dark",
  colors: {
    light: { primary: "#112233", secondary: "#223344", accent: "#334455", ground: "#fafafa", surface: "#ffffff", tint: "#eeeeee", ink: "#000000", ink_soft: "#444444", line: "#cccccc", error: "#aa0000", success: "#00aa00" },
    dark: { primary: "#aabbcc", ground: "#000000" },
  },
  typography: { heading_family: "Test Sans, sans-serif", base_size_px: 12, font_faces: [{ family: "Test Sans", src: "http://x/test.woff2", weight: "500" }], google_fonts: ["Hanken Grotesk:wght@400;700"] },
  shape: { radius_button: "999px" },
  layout: { immersive_intro: true, logo_placement: "top-right", content_max_width: "700px" },
  assets: { favicon: "http://x/fav.svg" },
  motion: { enabled: false },
  strings: { "intro.start": { en: "Begin", es: "Comenzar" } },
};

describe("applyTheme", () => {
  it("generates tokens, fallbacks, font faces, dark palette and motion override", () => {
    const css = themeCss(theme);
    expect(css).toContain("--p-primary: #112233;");
    expect(css).toContain("--p-primary-deep: #112233;"); // fallback to primary
    expect(css).toContain("--p-on-primary: #ffffff;");
    expect(css).toContain("--p-focus: #334455;"); // fallback to accent
    expect(css).toContain("--p-base-size: 16px;"); // clamped minimum
    expect(css).toContain("--p-radius-button: 999px;");
    expect(css).toContain('@font-face { font-family: "Test Sans"; src: url("http://x/test.woff2") format("woff2"); font-weight: 500;');
    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("--p-ground: #000000;");
    expect(css).toContain("animation-duration: 0.01ms");
  });

  it("applies to the document idempotently and merges strings", () => {
    applyTheme(theme);
    applyTheme(theme);
    expect(document.querySelectorAll("#prolog-theme")).toHaveLength(1);
    expect(document.documentElement.dataset.theme).toBe("test");
    expect(document.documentElement.dataset.logo).toBe("top-right");
    expect(document.querySelector<HTMLLinkElement>("#prolog-theme-fonts")?.href).toContain("family=Hanken+Grotesk:wght@400;700");
    expect(document.querySelector<HTMLLinkElement>('link[rel="icon"]')?.href).toBe("http://x/fav.svg");
    expect(document.querySelector<HTMLMetaElement>('meta[name="color-scheme"]')?.content).toBe("light dark");
    expect(i18n.t("intro.start")).toBe("Begin");
    expect(i18n.getResource("es", "translation", "intro.start")).toBe("Comenzar");
  });

  it("carries the light palette's explicit values into a dark palette that overrides a subset", () => {
    const css = themeCss({
      ...theme,
      colors: { light: { ...theme.colors.light, primary: "#ffe066", on_primary: "#1a1a1a", primary_deep: "#c9a800" }, dark: { primary: "#ffd23f" } },
    });
    const dark = css.slice(css.indexOf("@media (prefers-color-scheme: dark)"));
    expect(dark).toContain("--p-primary: #ffd23f;");
    expect(dark).not.toContain("--p-on-primary: #ffffff;");
    expect(dark).not.toContain("--p-primary-deep: #ffd23f;");
    // Unchanged tokens stay with the light block's values (cascade), not repeated.
    expect(dark).not.toContain("--p-secondary:");
  });

  it("derives the dark fallbacks from the effective palette when light set none", () => {
    const css = themeCss({ ...theme, colors: { light: theme.colors.light, dark: { primary: "#aabbcc" } } });
    const dark = css.slice(css.indexOf("@media (prefers-color-scheme: dark)"));
    expect(dark).toContain("--p-primary-deep: #aabbcc;");
    expect(dark).not.toContain("--p-on-primary:"); // white in both schemes: nothing to repeat
  });

  it("removes a previous theme's favicon when the next theme has none", () => {
    applyTheme(theme);
    expect(document.querySelector<HTMLLinkElement>('link[rel="icon"]')?.href).toBe("http://x/fav.svg");
    applyTheme({ ...theme, code: "plain", assets: {} });
    expect(document.querySelector('link[rel="icon"]')).toBeNull();
    applyTheme({ ...theme, code: "again" });
    expect(document.querySelectorAll('link[rel="icon"]')).toHaveLength(1);
  });
});
