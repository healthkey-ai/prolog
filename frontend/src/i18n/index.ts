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
  resources,
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

/** Merge extra chrome strings (e.g. from a theme's `strings`) at runtime. */
export function addStrings(overrides: Record<string, Record<string, string>>): void {
  const byLang: Record<string, Record<string, string>> = {};
  for (const [key, langs] of Object.entries(overrides)) {
    for (const [lang, text] of Object.entries(langs)) (byLang[lang] ??= {})[key] = text;
  }
  for (const [lang, bundle] of Object.entries(byLang)) i18n.addResourceBundle(lang, "translation", bundle, true, true);
}

export default i18n;
