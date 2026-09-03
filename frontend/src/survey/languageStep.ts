/**
 * Whether to ask for a language before the intro, rather than on it.
 *
 * The intro and the consent notice are what a respondent has to understand
 * before agreeing to anything, so a survey launched in several languages at
 * once may want that choice made first. `presentation.language_step` decides:
 *
 * - `inline` (default) — the picker sits on the intro, which is rendered in the
 *   browser's language until it is changed. Today's behaviour.
 * - `first` — a step ahead of the intro.
 * - `auto` — that step only when the browser is asking for a language the
 *   survey does not offer, which is when the default would be a guess.
 *
 * Pure so it can be tested without a router or a browser.
 */
export function needsLanguageStep(options: {
  languages: readonly string[];
  mode: "inline" | "first" | "auto" | undefined;
  /** Languages the browser asks for, most preferred first (navigator.languages). */
  preferred: readonly string[];
  /** A language named by the link, e.g. ?lang=es. */
  requested?: string;
}): boolean {
  const { languages, mode = "inline", preferred, requested } = options;
  // Nothing to choose between.
  if (languages.length < 2) return false;
  // A link that already names a language the survey offers has asked on the
  // respondent's behalf; asking again is a question they have answered.
  if (requested && languages.includes(requested)) return false;
  if (mode === "first") return true;
  if (mode === "auto") return !preferred.some((tag) => languages.includes(baseTag(tag)));
  return false;
}

/** "es-419" and "es-ES" are both Spanish as far as a survey's language list goes. */
export function baseTag(tag: string): string {
  return tag.toLowerCase().split("-")[0];
}
