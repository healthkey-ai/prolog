/**
 * A language's own name for pickers ("Español" for "es"), from the runtime's
 * Intl.DisplayNames; the uppercased code when the runtime cannot name it.
 */
export function languageName(code: string): string {
  try {
    const name = new Intl.DisplayNames([code], { type: "language" }).of(code);
    if (name && name !== code) return name.charAt(0).toLocaleUpperCase(code) + name.slice(1);
  } catch {
    // Unsupported locale tag or no Intl.DisplayNames: fall through to the code.
  }
  return code.toUpperCase();
}
