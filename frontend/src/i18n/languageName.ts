const LANGUAGE_NAMES: Record<string, string> = {
  en: "English",
  es: "Español",
  pt: "Português",
  fr: "Français",
  de: "Deutsch",
  it: "Italiano",
  nl: "Nederlands",
};

/** A language's own name for pickers; the code itself when unknown. */
export function languageName(code: string): string {
  return LANGUAGE_NAMES[code] ?? code.toUpperCase();
}
