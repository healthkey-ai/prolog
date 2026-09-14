/**
 * A language's own name for pickers ("Español" for "es"), from the runtime's
 * Intl.DisplayNames; the uppercased code when the runtime cannot name it.
 */
export function languageName(code: string): string {
  try {
    const name = new Intl.DisplayNames([code], { type: "language" }).of(code);
    if (name && name !== code)
      return name.charAt(0).toLocaleUpperCase(code) + name.slice(1);
  } catch {
    // Unsupported locale tag or no Intl.DisplayNames: fall through to the code.
  }
  return code.toUpperCase();
}

/**
 * A language's name in another language ("Spanish" for "es" read in English),
 * for the line under its own name in a picker; undefined when the runtime
 * cannot say. The reader's language, not always English: a Spanish reader is
 * told "Inglés", not "English".
 */
export function languageNameIn(
  code: string,
  readerLanguage: string,
): string | undefined {
  try {
    const name = new Intl.DisplayNames([readerLanguage], {
      type: "language",
    }).of(code);
    if (name && name !== code)
      return name.charAt(0).toLocaleUpperCase(readerLanguage) + name.slice(1);
  } catch {
    // Unsupported locale tag or no Intl.DisplayNames.
  }
  return undefined;
}
