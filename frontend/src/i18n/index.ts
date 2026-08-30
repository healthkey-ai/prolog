import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import es from "./es.json";
import fr from "./fr.json";
import pt from "./pt.json";

/**
 * Runner chrome strings. Survey content never lives here; it comes localized
 * from the API. A theme may override any key per language (THM-6).
 */
export const resources: Record<string, { translation: Record<string, string> }> = {
  en: { translation: en },
  es: { translation: es },
  fr: { translation: fr },
  pt: { translation: pt },
};

void i18n.use(initReactI18next).init({
  // i18next keeps what it is given and merges overrides into it in place; the
  // bundled originals stay pristine so addStrings can restore them.
  resources: structuredClone(resources),
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

/** Languages the previous `addStrings` call added beyond the bundled ones; they exist only as overrides. */
let extraLanguages: string[] = [];

/**
 * Merge extra chrome strings (e.g. from a theme's `strings`) at runtime. The
 * base bundles are restored first, and languages only the previous theme
 * brought are dropped, so a previous theme's overrides do not leak into the
 * next survey opened in the same session.
 */
export function addStrings(overrides: Record<string, Record<string, string>>): void {
  for (const [lang, base] of Object.entries(resources)) i18n.addResourceBundle(lang, "translation", { ...base.translation }, false, true);
  for (const lang of extraLanguages) i18n.removeResourceBundle(lang, "translation");
  const byLang: Record<string, Record<string, string>> = {};
  for (const [key, langs] of Object.entries(overrides)) {
    for (const [lang, text] of Object.entries(langs)) (byLang[lang] ??= {})[key] = text;
  }
  for (const [lang, bundle] of Object.entries(byLang)) i18n.addResourceBundle(lang, "translation", bundle, true, true);
  extraLanguages = Object.keys(byLang).filter((lang) => !(lang in resources));
}

export default i18n;
